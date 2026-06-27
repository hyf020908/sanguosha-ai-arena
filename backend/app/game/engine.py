from __future__ import annotations

import random
import uuid
from itertools import combinations

from app.game.deck import build_deck
from app.game.rules import CARD_LABELS, ROLE_SETS
from app.llm.client import LLMClient
from app.llm.prompt import compact_prompt
from app.models import AIConfig, Action, Card, CreateGameRequest, GameState, PendingResponse, Player


class GameEngine:
    def __init__(self) -> None:
        self.llm_client = LLMClient()

    def create_game(self, request: CreateGameRequest) -> GameState:
        total_players = 1 + len(request.ai_players)
        if total_players not in ROLE_SETS:
            raise ValueError("v0.1 仅支持 2 到 6 名玩家")

        rng = random.Random(request.seed) if request.seed is not None else random.Random()
        roles = ROLE_SETS[total_players].copy()
        rng.shuffle(roles)
        players: list[Player] = [
            Player(id="p0", name=request.human_name or "Human", is_human=True, role=roles[0])
        ]
        for index, ai_config in enumerate(request.ai_players, start=1):
            name = ai_config.name or f"AI-{index}"
            players.append(
                Player(
                    id=f"p{index}",
                    name=name,
                    is_human=False,
                    role=roles[index],
                    ai_config=ai_config.model_copy(update={"name": name}),
                )
            )

        for player in players:
            if player.role == "zhu":
                player.max_hp = 5
                player.hp = 5
                player.role_public = True

        deck = build_deck(rng)
        state = GameState(
            game_id=str(uuid.uuid4()),
            players=players,
            ai_timeout_seconds=request.ai_timeout_seconds,
            deck=deck,
        )
        for _ in range(4):
            for player in state.players:
                self._draw_cards(state, player, 1)

        state.current_player_index = next(i for i, player in enumerate(players) if player.role == "zhu")
        self._event(state, f"{self.current_player(state).name} 作为主公开启第 1 轮")
        self.start_turn(state)
        self.refresh_legal_actions(state)
        return state

    def current_player(self, state: GameState) -> Player:
        return state.players[state.current_player_index]

    def refresh_legal_actions(self, state: GameState) -> list[Action]:
        state.legal_actions = self.legal_actions(state)
        return state.legal_actions

    def legal_actions(self, state: GameState) -> list[Action]:
        if state.winner:
            return []
        if state.pending_response:
            return self._pending_actions(state, state.pending_response)

        player = self.current_player(state)
        if not player.alive or state.phase != "play":
            return []

        actions: list[Action] = []
        if not player.used_sha_this_turn and any(card.name == "sha" for card in player.hand):
            for target in state.players:
                if target.alive and target.id != player.id:
                    actions.append(
                        Action(
                            action_id=f"play_sha:{target.id}",
                            type="play_card",
                            card_name="sha",
                            target_player_id=target.id,
                            label=f"对 {target.name} 使用杀",
                        )
                    )
        if player.hp < player.max_hp and any(card.name == "tao" for card in player.hand):
            actions.append(
                Action(
                    action_id="play_tao",
                    type="play_card",
                    card_name="tao",
                    target_player_id=player.id,
                    label="使用桃回复 1 点体力",
                )
            )
        actions.append(Action(action_id="end_phase", type="end_phase", label="结束出牌阶段"))
        return actions

    def execute_action(self, state: GameState, action_id: str) -> None:
        actions = self.refresh_legal_actions(state)
        action = next((item for item in actions if item.action_id == action_id), None)
        if action is None:
            raise ValueError("非法 action_id：当前状态不允许执行该动作")

        if action.type == "play_card" and action.card_name == "sha":
            self._play_sha(state, action)
        elif action.type == "play_card" and action.card_name == "tao":
            self._play_tao(state, action)
        elif action.type == "end_phase":
            self._enter_discard_or_next(state)
        elif action.type == "respond_shan":
            self._respond_shan(state, action)
        elif action.type == "pass_response":
            self._pass_response(state)
        elif action.type == "dying_tao":
            self._dying_tao(state, action)
        elif action.type == "accept_death":
            self._kill_pending_player(state)
        elif action.type == "discard_cards":
            self._discard_cards(state, action)
        else:
            raise ValueError("未支持的动作类型")

        self._check_winner(state)
        self.refresh_legal_actions(state)

    async def auto_advance_until_human(self, state: GameState, max_steps: int = 40) -> None:
        steps = 0
        while not state.winner and steps < max_steps:
            self.refresh_legal_actions(state)
            actor = self._actor_waiting_for_action(state)
            if actor is None or actor.is_human:
                break
            await self.step_ai(state)
            steps += 1
        self.refresh_legal_actions(state)

    async def step_ai(self, state: GameState) -> str:
        self.refresh_legal_actions(state)
        actor = self._actor_waiting_for_action(state)
        if actor is None:
            return "当前没有需要 AI 执行的动作"
        if actor.is_human:
            return "当前等待人类玩家操作"

        legal = state.legal_actions
        if not legal:
            return "当前没有合法动作"

        chosen = None
        if actor.ai_config:
            payload = compact_prompt(state, actor, legal)
            chosen = await self.llm_client.choose_action(actor.ai_config, payload, legal, state.ai_timeout_seconds)
        if chosen is None:
            chosen = self._default_action_id(legal)
            self._event(state, f"{actor.name} 使用默认动作")
        self.execute_action(state, chosen)
        return f"{actor.name} 执行 {chosen}"

    def start_turn(self, state: GameState) -> None:
        player = self.current_player(state)
        while not player.alive:
            self._advance_to_next_player(state)
            player = self.current_player(state)

        state.phase = "draw"
        state.pending_response = None
        player.used_sha_this_turn = False
        self._draw_cards(state, player, 2)
        self._event(state, f"{player.name} 摸了 2 张牌")
        state.phase = "play"

    def _pending_actions(self, state: GameState, pending: PendingResponse) -> list[Action]:
        player = self._player_by_id(state, pending.player_id)
        if not player.alive:
            return []

        if pending.type == "respond_shan":
            actions = []
            if any(card.name == "shan" for card in player.hand):
                actions.append(
                    Action(
                        action_id="respond_shan",
                        type="respond_shan",
                        card_name="shan",
                        label="出闪",
                    )
                )
            actions.append(Action(action_id="pass_response", type="pass_response", label="不出闪"))
            return actions

        if pending.type == "dying_tao":
            actions = []
            if any(card.name == "tao" for card in player.hand):
                actions.append(
                    Action(
                        action_id="dying_tao",
                        type="dying_tao",
                        card_name="tao",
                        label="使用桃自救",
                    )
                )
            actions.append(Action(action_id="accept_death", type="accept_death", label="不使用桃"))
            return actions

        if pending.type == "discard":
            required = pending.required_count or max(0, len(player.hand) - max(player.hp, 0))
            if required <= 0:
                return [Action(action_id="discard:none", type="discard_cards", target_card_ids=[], label="无需弃牌")]
            actions: list[Action] = []
            for combo in combinations(player.hand, required):
                ids = [card.id for card in combo]
                names = "、".join(CARD_LABELS[card.name] for card in combo)
                actions.append(
                    Action(
                        action_id=f"discard:{','.join(ids)}",
                        type="discard_cards",
                        target_card_ids=ids,
                        label=f"弃置 {names}",
                    )
                )
            return actions[:120]
        return []

    def _play_sha(self, state: GameState, action: Action) -> None:
        player = self.current_player(state)
        target = self._player_by_id(state, action.target_player_id or "")
        card = self._take_random_card_by_name(player, "sha")
        state.discard_pile.append(card)
        player.used_sha_this_turn = True
        self._event(state, f"{player.name} 对 {target.name} 使用杀")

        if any(card.name == "shan" for card in target.hand):
            state.phase = "response"
            state.pending_response = PendingResponse(
                type="respond_shan",
                player_id=target.id,
                source_player_id=player.id,
                card_id=card.id,
            )
        else:
            self._damage(state, target, player)

    def _play_tao(self, state: GameState, action: Action) -> None:
        player = self.current_player(state)
        card = self._take_random_card_by_name(player, "tao")
        state.discard_pile.append(card)
        player.hp = min(player.max_hp, player.hp + 1)
        self._event(state, f"{player.name} 使用桃回复 1 点体力")

    def _respond_shan(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有响应")
        player = self._player_by_id(state, pending.player_id)
        source = self._player_by_id(state, pending.source_player_id or "")
        card = self._take_random_card_by_name(player, "shan")
        state.discard_pile.append(card)
        self._event(state, f"{player.name} 打出闪，抵消了杀")
        state.current_player_index = state.players.index(source)
        state.phase = "play"
        state.pending_response = None

    def _pass_response(self, state: GameState) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有响应")
        target = self._player_by_id(state, pending.player_id)
        source = self._player_by_id(state, pending.source_player_id or "")
        self._event(state, f"{target.name} 未出闪")
        state.current_player_index = state.players.index(source)
        state.pending_response = None
        self._damage(state, target, source)

    def _damage(self, state: GameState, target: Player, source: Player) -> None:
        target.hp -= 1
        self._event(state, f"{target.name} 受到 1 点伤害")
        if target.hp <= 0:
            state.phase = "response"
            state.pending_response = PendingResponse(
                type="dying_tao",
                player_id=target.id,
                source_player_id=source.id,
            )
        else:
            state.current_player_index = state.players.index(source)
            state.phase = "play"

    def _dying_tao(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有濒死响应")
        player = self._player_by_id(state, pending.player_id)
        source = self._player_by_id(state, pending.source_player_id or player.id)
        card = self._take_random_card_by_name(player, "tao")
        state.discard_pile.append(card)
        player.hp += 1
        self._event(state, f"{player.name} 使用桃脱离濒死")
        state.pending_response = None
        state.current_player_index = state.players.index(source)
        state.phase = "play"

    def _kill_pending_player(self, state: GameState) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有濒死响应")
        player = self._player_by_id(state, pending.player_id)
        source = self._player_by_id(state, pending.source_player_id or player.id)
        player.alive = False
        player.hp = 0
        state.discard_pile.extend(player.hand)
        player.hand = []
        self._event(state, f"{player.name} 死亡")
        state.pending_response = None
        if not state.winner:
            state.current_player_index = state.players.index(source if source.alive else self.current_player(state))
            state.phase = "play"

    def _enter_discard_or_next(self, state: GameState) -> None:
        player = self.current_player(state)
        state.phase = "discard"
        required = max(0, len(player.hand) - max(player.hp, 0))
        if required > 0:
            state.pending_response = PendingResponse(type="discard", player_id=player.id, required_count=required)
            self._event(state, f"{player.name} 需要弃置 {required} 张牌")
        else:
            self._event(state, f"{player.name} 结束回合")
            self._advance_to_next_player(state)
            self.start_turn(state)

    def _discard_cards(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有弃牌要求")
        player = self._player_by_id(state, pending.player_id)
        for card_id in action.target_card_ids or []:
            state.discard_pile.append(self._take_card(player, card_id))
        self._event(state, f"{player.name} 弃置了 {len(action.target_card_ids or [])} 张牌")
        state.pending_response = None
        self._advance_to_next_player(state)
        self.start_turn(state)

    def _check_winner(self, state: GameState) -> None:
        if state.winner:
            return
        lord = next(player for player in state.players if player.role == "zhu")
        if not lord.alive:
            state.winner = "fan"
            state.phase = "game_over"
            state.pending_response = None
            self._event(state, "主公死亡，反贼胜利")
            return
        rebels_alive = any(player.alive and player.role == "fan" for player in state.players)
        if not rebels_alive:
            state.winner = "zhu"
            state.phase = "game_over"
            state.pending_response = None
            self._event(state, "所有反贼死亡，主公阵营胜利")

    def _actor_waiting_for_action(self, state: GameState) -> Player | None:
        if state.winner:
            return None
        if state.pending_response:
            return self._player_by_id(state, state.pending_response.player_id)
        if state.phase == "play":
            return self.current_player(state)
        return None

    def _default_action_id(self, legal: list[Action]) -> str:
        for preferred in ("end_phase", "pass_response", "accept_death"):
            if any(action.action_id == preferred for action in legal):
                return preferred
        for action in legal:
            if action.type == "discard_cards":
                return action.action_id
        return legal[0].action_id

    def _advance_to_next_player(self, state: GameState) -> None:
        previous = state.current_player_index
        total = len(state.players)
        for offset in range(1, total + 1):
            candidate = (previous + offset) % total
            if state.players[candidate].alive:
                state.current_player_index = candidate
                if candidate <= previous:
                    state.round += 1
                return

    def _draw_cards(self, state: GameState, player: Player, count: int) -> None:
        for _ in range(count):
            if not state.deck:
                self._reshuffle_discard(state)
            if state.deck:
                player.hand.append(state.deck.pop(0))
        player.hand_count = len(player.hand)

    def _reshuffle_discard(self, state: GameState) -> None:
        if not state.discard_pile:
            return
        rng = random.Random()
        state.deck = state.discard_pile
        state.discard_pile = []
        rng.shuffle(state.deck)
        self._event(state, "弃牌堆重新洗入牌堆")

    def _take_card(self, player: Player, card_id: str) -> Card:
        for index, card in enumerate(player.hand):
            if card.id == card_id:
                taken = player.hand.pop(index)
                player.hand_count = len(player.hand)
                return taken
        raise ValueError("找不到指定手牌")

    def _take_random_card_by_name(self, player: Player, card_name: str) -> Card:
        candidates = [index for index, card in enumerate(player.hand) if card.name == card_name]
        if not candidates:
            raise ValueError("找不到指定类型手牌")
        index = random.choice(candidates)
        taken = player.hand.pop(index)
        player.hand_count = len(player.hand)
        return taken

    def _player_by_id(self, state: GameState, player_id: str) -> Player:
        for player in state.players:
            if player.id == player_id:
                return player
        raise ValueError("找不到指定玩家")

    def _event(self, state: GameState, message: str) -> None:
        state.recent_events.append(message)
        state.recent_events = state.recent_events[-20:]
