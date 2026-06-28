from __future__ import annotations

import random
import uuid
import logging
from collections import Counter
from itertools import combinations

from app.game.deck import build_deck
from app.game.rules import (
    ARMOR_CARDS,
    ATTACK_HORSES,
    BLACK_SUITS,
    CARD_LABELS,
    DEFENSE_HORSES,
    DELAYED_TRICKS,
    EQUIPMENT_CARDS,
    RED_SUITS,
    ROLE_SETS,
    TRICK_CARDS,
    WEAPON_RANGES,
    attack_range,
    distance_between,
    in_attack_range,
)
from app.llm.client import LLMClient
from app.llm.prompt import compact_prompt
from app.models import AIConfig, Action, Card, CardName, CreateGameRequest, GameState, PendingResponse, Player
from app.storage.events import game_events


logger = logging.getLogger(__name__)


class GameEngine:
    def __init__(self) -> None:
        self.llm_client = LLMClient()

    def create_game(self, request: CreateGameRequest) -> GameState:
        total_players = 1 + len(request.ai_players)
        if total_players not in ROLE_SETS:
            raise ValueError("v0.2 仅支持 2 到 6 名玩家")

        rng = random.Random(request.seed) if request.seed is not None else random.Random()
        roles = ROLE_SETS[total_players].copy()
        rng.shuffle(roles)
        players = [Player(id="p0", name=request.human_name or "Human", is_human=True, role=roles[0])]
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

        state = GameState(game_id=str(uuid.uuid4()), players=players, ai_timeout_seconds=request.ai_timeout_seconds, deck=build_deck(rng))
        for _ in range(4):
            for player in state.players:
                self._draw_cards(state, player, 1)

        state.current_player_index = next(index for index, player in enumerate(players) if player.role == "zhu")
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
        cards_by_name: dict[CardName, list[Card]] = {}
        for card in player.hand:
            cards_by_name.setdefault(card.name, []).append(card)

        for card in cards_by_name.get("sha", []):
            if self._can_use_sha(player):
                for target in self._alive_opponents(state, player):
                    if self._in_attack_range(state, player, target):
                        actions.append(self._card_action(f"play_sha:{card.id}:{target.id}", "play_card", card, target, f"杀 → {target.name}"))

        for card in cards_by_name.get("tao", []):
            for target in [item for item in state.players if item.alive and item.hp < item.max_hp]:
                actions.append(self._card_action(f"play_tao:{card.id}:{target.id}", "play_card", card, target, f"桃 → {target.name}"))

        for card in cards_by_name.get("wuzhongshengyou", []):
            actions.append(self._card_action(f"play_wuzhongshengyou:{card.id}:{player.id}", "play_card", card, player, "无中生有"))

        if any(target.alive and target.hp < target.max_hp for target in state.players):
            for card in cards_by_name.get("taoyuanjieyi", []):
                actions.append(self._card_action(f"play_taoyuanjieyi:{card.id}", "play_card", card, None, "桃园结义"))

        for card in cards_by_name.get("wugufengdeng", []):
            actions.append(self._card_action(f"play_wugufengdeng:{card.id}", "play_card", card, None, "五谷丰登"))

        if self._alive_opponents(state, player):
            for card in cards_by_name.get("nanmanruqin", []):
                actions.append(self._card_action(f"play_nanmanruqin:{card.id}", "play_card", card, None, "南蛮入侵"))
            for card in cards_by_name.get("wanjianqifa", []):
                actions.append(self._card_action(f"play_wanjianqifa:{card.id}", "play_card", card, None, "万箭齐发"))

        for card in cards_by_name.get("juedou", []):
            for target in self._alive_opponents(state, player):
                actions.append(self._card_action(f"play_juedou:{card.id}:{target.id}", "play_card", card, target, f"决斗 → {target.name}"))

        for card in cards_by_name.get("guohechaiqiao", []):
            for target in [item for item in self._alive_opponents(state, player) if self._has_any_card(item)]:
                actions.extend(self._area_target_actions(card, target, "guohechaiqiao"))

        for card in cards_by_name.get("shunshouqianyang", []):
            for target in self._alive_opponents(state, player):
                if self._distance(state, player, target) <= 1 and self._has_any_card(target):
                    actions.extend(self._area_target_actions(card, target, "shunshouqianyang"))

        for card in cards_by_name.get("jiedaosharen", []):
            for target in self._alive_opponents(state, player):
                if not target.equipment.weapon:
                    continue
                for victim in self._alive_opponents(state, target):
                    if self._in_attack_range(state, target, victim):
                        actions.append(
                            self._card_action(
                                f"play_jiedaosharen:{card.id}:{target.id}:{victim.id}",
                                "play_card",
                                card,
                                target,
                                f"借刀杀人 → {target.name} 杀 {victim.name}",
                                secondary_target=victim,
                            )
                        )

        for card in cards_by_name.get("lebusishu", []):
            for target in self._alive_opponents(state, player):
                if not self._has_delayed_trick(target, "lebusishu"):
                    actions.append(self._card_action(f"play_lebusishu:{card.id}:{target.id}", "play_card", card, target, f"乐不思蜀 → {target.name}"))

        for card in cards_by_name.get("shandian", []):
            if not self._has_delayed_trick(player, "shandian"):
                actions.append(self._card_action(f"play_shandian:{card.id}:{player.id}", "play_card", card, player, "闪电"))

        for card in sorted([item for item in player.hand if item.name in EQUIPMENT_CARDS], key=lambda item: CARD_LABELS[item.name]):
            actions.append(self._card_action(f"equip:{card.id}", "equip_card", card, player, f"装备：{CARD_LABELS[card.name]}"))

        actions.append(Action(action_id="end_phase", type="end_phase", label="结束出牌阶段"))
        return actions

    def execute_action(self, state: GameState, action_id: str) -> None:
        actions = self.refresh_legal_actions(state)
        action = next((item for item in actions if item.action_id == action_id), None)
        if action is None:
            raise ValueError("非法 action_id：当前状态不允许执行该动作")

        if action.type == "play_card":
            self._play_card(state, action)
        elif action.type == "equip_card":
            self._equip_card(state, action)
        elif action.type == "end_phase":
            self._enter_discard_or_next(state)
        elif action.type == "respond_shan":
            self._respond_with_card(state, action)
        elif action.type == "respond_sha":
            self._respond_with_card(state, action)
        elif action.type == "pass_response":
            self._pass_response(state)
        elif action.type == "dying_tao":
            self._dying_tao(state, action)
        elif action.type == "wuxie":
            self._respond_wuxie(state, action)
        elif action.type == "discard_cards":
            self._discard_cards(state, action)
        elif action.type == "wugu_choose":
            self._choose_wugu_card(state, action)
        else:
            raise ValueError("未支持的动作类型")

        self._check_winner(state)
        self.refresh_legal_actions(state)

    async def auto_advance_until_human(self, state: GameState, max_steps: int = 80) -> None:
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

        legal = self.ai_legal_actions(state, actor, state.legal_actions)
        if not legal:
            return "当前没有合法动作"

        chosen = None
        if len(state.legal_actions) == 1:
            chosen = state.legal_actions[0].action_id
            logger.info(
                "AI action auto-selected because only one legal action exists: ai=%s action_id=%s",
                actor.name,
                chosen,
            )
        elif actor.ai_config:
            payload = compact_prompt(state, actor, legal)
            chosen = await self.llm_client.choose_action(actor.ai_config, payload, legal, state.ai_timeout_seconds)
        if chosen is None:
            chosen = self._default_action_id(legal)
            self._event(state, f"{actor.name} 使用默认动作")
        self.execute_action(state, chosen)
        return f"{actor.name} 执行 {chosen}"

    def ai_legal_actions(self, state: GameState, actor: Player, legal_actions: list[Action]) -> list[Action]:
        filtered = [action for action in legal_actions if self._ai_action_allowed_by_role(state, actor, action)]
        if not filtered:
            filtered = [action for action in legal_actions if action.type != "play_card" or action.card_name not in {"sha", "juedou"}]
        return self._ai_ranked_actions(state, actor, filtered) or filtered

    def start_turn(self, state: GameState) -> None:
        player = self.current_player(state)
        while not player.alive:
            self._advance_to_next_player(state)
            player = self.current_player(state)

        state.phase = "judge"
        state.pending_response = None
        player.used_sha_this_turn = False
        self._resolve_judgment_area(state, player)
        if state.pending_response or state.winner:
            return
        if state.phase == "play":
            return
        state.phase = "draw"
        self._draw_cards(state, player, 2)
        self._event(state, f"{player.name} 摸了 2 张牌")
        state.phase = "play"

    def _pending_actions(self, state: GameState, pending: PendingResponse) -> list[Action]:
        player = self._player_by_id(state, pending.player_id)
        if not player.alive:
            return []

        if pending.type == "respond_shan":
            actions = []
            for card in [item for item in player.hand if item.name == "shan"]:
                actions.append(self._card_action(f"respond_shan:{card.id}", "respond_shan", card, None, "闪"))
            actions.append(Action(action_id="pass_response", type="pass_response", label="不出闪"))
            return actions

        if pending.type == "respond_sha":
            actions = []
            target = self._player_by_id(state, pending.target_player_id) if pending.target_player_id else None
            for card in [item for item in player.hand if item.name == "sha"]:
                label = f"杀 → {target.name}" if pending.effect_type == "jiedaosharen" and target else "杀"
                actions.append(self._card_action(f"respond_sha:{card.id}", "respond_sha", card, target, label))
            pass_label = "不出杀，交出武器" if pending.effect_type == "jiedaosharen" else "不出杀"
            actions.append(Action(action_id="pass_response", type="pass_response", label=pass_label))
            return actions

        if pending.type == "wuxie":
            actions = []
            for card in [item for item in player.hand if item.name == "wuxiekeji"]:
                actions.append(self._card_action(f"wuxie:{card.id}", "wuxie", card, None, "无懈可击"))
            actions.append(Action(action_id="pass_response", type="pass_response", label="不使用无懈可击"))
            return actions

        if pending.type == "dying_tao":
            actions = []
            target = self._player_by_id(state, pending.target_player_id or pending.player_id)
            for card in [item for item in player.hand if item.name == "tao"]:
                label = "使用桃自救" if target.id == player.id else f"对 {target.name} 使用桃"
                actions.append(self._card_action(f"dying_tao:{card.id}", "dying_tao", card, target, label))
            actions.append(Action(action_id="pass_response", type="pass_response", label="不使用桃"))
            return actions

        if pending.type == "wugu":
            actions = []
            for card in pending.wugu_pool or []:
                actions.append(self._card_action(f"wugu_choose:{card.id}", "wugu_choose", card, player, f"选择 {CARD_LABELS[card.name]}"))
            return actions

        if pending.type == "discard":
            required = pending.required_count or max(0, len(player.hand) - max(player.hp, 0))
            if required <= 0:
                return [Action(action_id="discard:none", type="discard_cards", target_card_ids=[], label="无需弃牌")]
            actions: list[Action] = []
            for combo in combinations(player.hand, required):
                card_ids = [card.id for card in combo]
                names = "、".join(self._card_brief(card) for card in combo)
                actions.append(Action(action_id=f"discard:{','.join(card_ids)}", type="discard_cards", target_card_ids=card_ids, label=f"弃置 {names}"))
            return actions[:120]
        return []

    def _play_card(self, state: GameState, action: Action) -> None:
        player = self.current_player(state)
        card_name = action.card_name
        if card_name in EQUIPMENT_CARDS:
            self._equip_card(state, action)
            return
        if card_name == "sha":
            self._play_sha(state, action)
        elif card_name == "tao":
            self._play_tao(state, action)
        elif card_name in TRICK_CARDS:
            self._play_trick(state, action)
        else:
            raise ValueError("未支持的牌")
        player.hand_count = len(player.hand)

    def _play_sha(self, state: GameState, action: Action) -> None:
        source = self.current_player(state)
        target = self._player_by_id(state, action.target_player_id or "")
        card = self._take_card(source, action.card_id or "")
        state.discard_pile.append(card)
        if source.equipment.weapon is None or source.equipment.weapon.name != "zhugeliannu":
            source.used_sha_this_turn = True
        self._event(state, f"{source.name} 对 {target.name} 使用杀")

        if self._armor_blocks_sha(state, source, target, card):
            self._event(state, f"{target.name} 的仁王盾抵消了黑色杀")
            state.phase = "play"
            return
        if self._bagua_success(state, source, target, effect_type="sha"):
            self._event(state, f"{target.name} 的八卦阵判定成功，视为出闪")
            state.phase = "play"
            return
        self._request_shan(state, source, target, effect_type="sha", origin_player_id=source.id)

    def _play_tao(self, state: GameState, action: Action) -> None:
        player = self.current_player(state)
        target = self._player_by_id(state, action.target_player_id or player.id)
        if not target.alive or target.hp >= target.max_hp:
            raise ValueError("桃只能对受伤的存活角色使用")
        card = self._take_card(player, action.card_id or "")
        state.discard_pile.append(card)
        target.hp = min(target.max_hp, target.hp + 1)
        self._event(state, f"{player.name} 对 {target.name} 使用桃回复 1 点体力")

    def _play_trick(self, state: GameState, action: Action) -> None:
        player = self.current_player(state)
        card_name = action.card_name
        card = self._take_card(player, action.card_id or "")
        if card_name in DELAYED_TRICKS:
            target = self._player_by_id(state, action.target_player_id or player.id)
            self._event(state, f"{player.name} 对 {target.name} 使用{CARD_LABELS[card_name]}")
            self._start_wuxie_or_apply(
                state,
                PendingResponse(
                    type="wuxie",
                    player_id="",
                    source_player_id=player.id,
                    origin_player_id=player.id,
                    target_player_id=target.id,
                    card_id=card.id,
                    card_name=card_name,
                    card_suit=card.suit,
                    card_rank=card.rank,
                    pending_card=card,
                    effect_type=card_name,
                ),
            )
            return

        state.discard_pile.append(card)
        self._event(state, f"{player.name} 使用{CARD_LABELS[card_name]}")
        if card_name in {"nanmanruqin", "wanjianqifa"}:
            targets = [target.id for target in self._alive_opponents(state, player)]
            self._continue_mass_trick(
                state,
                PendingResponse(
                    type="wuxie",
                    player_id="",
                    source_player_id=player.id,
                    origin_player_id=player.id,
                    card_id=card.id,
                    card_name=card_name,
                    card_suit=card.suit,
                    card_rank=card.rank,
                    effect_type=card_name,
                    target_player_ids=targets,
                    remaining_player_ids=targets,
                ),
            )
            return
        if card_name == "taoyuanjieyi":
            targets = [target.id for target in state.players if target.alive and target.hp < target.max_hp]
            self._continue_mass_trick(
                state,
                PendingResponse(
                    type="wuxie",
                    player_id="",
                    source_player_id=player.id,
                    origin_player_id=player.id,
                    card_id=card.id,
                    card_name=card_name,
                    card_suit=card.suit,
                    card_rank=card.rank,
                    effect_type=card_name,
                    target_player_ids=targets,
                    remaining_player_ids=targets,
                ),
            )
            return
        if card_name == "wugufengdeng":
            self._start_wuxie_or_apply(
                state,
                PendingResponse(
                    type="wuxie",
                    player_id="",
                    source_player_id=player.id,
                    origin_player_id=player.id,
                    card_id=card.id,
                    card_name=card_name,
                    card_suit=card.suit,
                    card_rank=card.rank,
                    effect_type=card_name,
                ),
            )
            return
        self._start_wuxie_or_apply(
            state,
            PendingResponse(
                type="wuxie",
                player_id="",
                source_player_id=player.id,
                origin_player_id=player.id,
                target_player_id=action.target_player_id,
                secondary_target_player_id=action.secondary_target_player_id,
                selected_area=action.selected_area,
                selected_card_id=action.selected_card_id,
                card_id=card.id,
                card_name=card_name,
                card_suit=card.suit,
                card_rank=card.rank,
                effect_type=card_name,
            ),
        )

    def _equip_card(self, state: GameState, action: Action) -> None:
        card_name = action.card_name
        if card_name is None:
            raise ValueError("缺少装备牌")
        player = self.current_player(state)
        card = self._take_card(player, action.card_id or "")
        old = None
        if card_name in WEAPON_RANGES:
            old = player.equipment.weapon
            player.equipment.weapon = card
        elif card_name in ARMOR_CARDS:
            old = player.equipment.armor
            player.equipment.armor = card
        elif card_name in ATTACK_HORSES:
            old = player.equipment.attack_horse
            player.equipment.attack_horse = card
        elif card_name in DEFENSE_HORSES:
            old = player.equipment.defense_horse
            player.equipment.defense_horse = card
        else:
            raise ValueError("未知装备")
        if old:
            state.discard_pile.append(old)
        self._event(state, f"{player.name} 装备{CARD_LABELS[card_name]}")

    def _start_wuxie_or_apply(self, state: GameState, context: PendingResponse) -> None:
        queue = self._wuxie_queue(state, context)
        if queue:
            context.player_id = queue[0]
            context.queue_player_ids = queue[1:]
            context.responded_player_ids = []
            state.phase = "response"
            state.pending_response = context
            self._event(state, self._wuxie_waiting_message(state, context))
        else:
            self._apply_trick_effect(state, context)

    def _finish_wuxie_chain(self, state: GameState, pending: PendingResponse) -> None:
        state.pending_response = None
        if pending.wuxie_effect_cancelled:
            if pending.pending_card:
                state.discard_pile.append(pending.pending_card)
            self._event(state, f"{CARD_LABELS[pending.card_name]}被无懈可击抵消")
            if pending.effect_type in {"nanmanruqin", "wanjianqifa", "taoyuanjieyi"} and pending.target_player_id:
                self._continue_mass_trick(state, pending)
            else:
                source_id = pending.origin_player_id or pending.source_player_id
                if source_id:
                    state.current_player_index = self._index_by_id(state, source_id)
                state.phase = "play"
            return
        if pending.effect_type in {"nanmanruqin", "wanjianqifa", "taoyuanjieyi"} and pending.target_player_id:
            self._apply_mass_target_effect(state, pending)
        else:
            self._apply_trick_effect(state, pending)

    def _respond_wuxie(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None or pending.type != "wuxie":
            raise ValueError("当前没有无懈可击响应")
        player = self._player_by_id(state, pending.player_id)
        card = self._take_card(player, action.card_id or "")
        state.discard_pile.append(card)
        pending.wuxie_effect_cancelled = not pending.wuxie_effect_cancelled
        state_name = "原锦囊将被抵消" if pending.wuxie_effect_cancelled else "上一张无懈被抵消，原锦囊继续生效"
        self._event(state, f"{player.name} 使用无懈可击，{state_name}")
        queue = self._wuxie_counter_queue(state, player.id)
        if queue:
            pending.player_id = queue[0]
            pending.queue_player_ids = queue[1:]
            pending.responded_player_ids = []
            state.pending_response = pending
            state.phase = "response"
            self._event(state, self._wuxie_waiting_message(state, pending))
            return
        self._finish_wuxie_chain(state, pending)

    def _pass_response(self, state: GameState) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有响应")

        player = self._player_by_id(state, pending.player_id)
        if pending.type == "wuxie":
            self._event(state, f"{player.name} 未使用无懈可击")
            queue = pending.queue_player_ids or []
            if queue:
                pending.responded_player_ids = (pending.responded_player_ids or []) + [player.id]
                pending.player_id = queue[0]
                pending.queue_player_ids = queue[1:]
                return
            self._finish_wuxie_chain(state, pending)
            return

        if pending.type == "dying_tao":
            self._pass_dying_tao(state)
            return

        if pending.type == "respond_shan":
            self._event(state, f"{player.name} 未出闪")
            state.pending_response = None
            source = self._player_by_id(state, pending.source_player_id or "")
            self._damage(state, player, source, pending)
            return

        if pending.type == "respond_sha":
            self._event(state, f"{player.name} 未出杀")
            state.pending_response = None
            source = self._player_by_id(state, pending.source_player_id or "")
            self._respond_sha_failed(state, player, source, pending)

    def _respond_with_card(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有响应")
        player = self._player_by_id(state, pending.player_id)
        source = self._player_by_id(state, pending.source_player_id or "")
        card = self._take_card(player, action.card_id or "")
        state.discard_pile.append(card)
        state.pending_response = None
        if pending.type == "respond_shan":
            self._event(state, f"{player.name} 打出闪")
            self._finish_response_context(state, pending)
        elif pending.type == "respond_sha" and pending.effect_type == "juedou":
            self._event(state, f"{player.name} 在决斗中打出杀")
            state.phase = "response"
            state.pending_response = PendingResponse(
                type="respond_sha",
                player_id=source.id,
                source_player_id=player.id,
                origin_player_id=pending.origin_player_id,
                target_player_id=pending.target_player_id,
                effect_type="juedou",
            )
        elif pending.type == "respond_sha" and pending.effect_type == "jiedaosharen":
            victim = self._player_by_id(state, pending.target_player_id or "")
            self._event(state, f"{player.name} 因借刀杀人对 {victim.name} 使用杀")
            if self._armor_blocks_sha(state, player, victim, card):
                self._event(state, f"{victim.name} 的仁王盾抵消了黑色杀")
                self._finish_response_context(state, pending)
            elif self._bagua_success(state, player, victim, effect_type="sha"):
                self._event(state, f"{victim.name} 的八卦阵判定成功，视为出闪")
                self._finish_response_context(state, pending)
            else:
                self._request_shan(
                    state,
                    player,
                    victim,
                    effect_type="jiedaosharen",
                    origin_player_id=pending.origin_player_id,
                )
        elif pending.type == "respond_sha":
            self._event(state, f"{player.name} 打出杀")
            self._finish_response_context(state, pending)

    def _apply_trick_effect(self, state: GameState, context: PendingResponse) -> None:
        source = self._player_by_id(state, context.source_player_id or context.origin_player_id or "")
        effect = context.effect_type or context.card_name
        if effect == "wuzhongshengyou":
            self._draw_cards(state, source, 2)
            self._event(state, f"{source.name} 因无中生有摸了 2 张牌")
        elif effect == "guohechaiqiao":
            target = self._player_by_id(state, context.target_player_id or "")
            if target.id == source.id:
                raise ValueError("过河拆桥不能对自己使用")
            discarded = self._remove_selected_card_from_area(target, context.selected_area, context.selected_card_id)
            state.discard_pile.append(discarded)
            self._event(state, f"{source.name} 拆掉了 {target.name} 的{self._area_label(context.selected_area)}：{CARD_LABELS[discarded.name]}")
        elif effect == "shunshouqianyang":
            target = self._player_by_id(state, context.target_player_id or "")
            if self._distance(state, source, target) > 1:
                raise ValueError("顺手牵羊目标距离不合法")
            gained = self._remove_selected_card_from_area(target, context.selected_area, context.selected_card_id)
            source.hand.append(gained)
            source.hand_count = len(source.hand)
            self._event(state, f"{source.name} 获得了 {target.name} 的{self._area_label(context.selected_area)}：{CARD_LABELS[gained.name]}")
        elif effect == "jiedaosharen":
            target = self._player_by_id(state, context.target_player_id or "")
            victim = self._player_by_id(state, context.secondary_target_player_id or "")
            if any(card.name == "sha" for card in target.hand):
                state.phase = "response"
                state.pending_response = PendingResponse(
                    type="respond_sha",
                    player_id=target.id,
                    source_player_id=target.id,
                    origin_player_id=source.id,
                    target_player_id=victim.id,
                    secondary_target_player_id=source.id,
                    card_name="jiedaosharen",
                    effect_type="jiedaosharen",
                )
                self._event(state, f"{target.name} 需要选择是否因借刀杀人对 {victim.name} 出杀")
                return
            elif target.equipment.weapon:
                source.hand.append(target.equipment.weapon)
                source.hand_count = len(source.hand)
                target.equipment.weapon = None
                self._event(state, f"{target.name} 未出杀，武器交给 {source.name}")
            state.phase = "play"
            state.current_player_index = self._index_by_id(state, source.id)
            return
        elif effect == "juedou":
            target = self._player_by_id(state, context.target_player_id or "")
            state.phase = "response"
            state.pending_response = PendingResponse(
                type="respond_sha",
                player_id=target.id,
                source_player_id=source.id,
                origin_player_id=source.id,
                target_player_id=target.id,
                effect_type="juedou",
            )
            return
        elif effect in {"nanmanruqin", "wanjianqifa", "taoyuanjieyi", "wugufengdeng"}:
            if effect == "wugufengdeng":
                self._start_wugu(state, source)
            else:
                self._continue_mass_trick(state, context)
            return
        elif effect == "lebusishu":
            target = self._player_by_id(state, context.target_player_id or "")
            if context.pending_card is None:
                raise ValueError("缺少乐不思蜀牌")
            target.judgment_area.append(context.pending_card)
            self._event(state, f"{CARD_LABELS[context.card_name]}进入 {target.name} 的判定区")
        elif effect == "shandian":
            target = self._player_by_id(state, context.target_player_id or source.id)
            if context.pending_card is None:
                raise ValueError("缺少闪电牌")
            target.judgment_area.append(context.pending_card)
            self._event(state, f"闪电进入 {target.name} 的判定区")
        state.current_player_index = self._index_by_id(state, source.id)
        state.phase = "play"

    def _continue_mass_trick(self, state: GameState, context: PendingResponse) -> None:
        source = self._player_by_id(state, context.source_player_id or context.origin_player_id or "")
        remaining = [player_id for player_id in (context.remaining_player_ids or []) if self._player_by_id(state, player_id).alive]
        if not remaining:
            state.current_player_index = self._index_by_id(state, source.id)
            state.phase = "play"
            state.pending_response = None
            return
        target = self._player_by_id(state, remaining[0])
        context.remaining_player_ids = remaining[1:]
        self._start_wuxie_or_apply_target(state, context, target)

    def _start_wuxie_or_apply_target(self, state: GameState, context: PendingResponse, target: Player) -> None:
        card_name = context.card_name or context.effect_type
        next_context = PendingResponse(
            type="wuxie",
            player_id="",
            source_player_id=context.source_player_id,
            origin_player_id=context.origin_player_id,
            target_player_id=target.id,
            card_id=context.card_id,
            card_name=card_name,
            card_suit=context.card_suit,
            card_rank=context.card_rank,
            effect_type=card_name,
            remaining_player_ids=context.remaining_player_ids,
        )
        queue = self._wuxie_queue(state, next_context)
        next_context.player_id = queue[0] if queue else ""
        next_context.queue_player_ids = queue[1:] if queue else []
        if queue:
            state.phase = "response"
            state.pending_response = next_context
            self._event(state, self._wuxie_waiting_message(state, next_context))
        else:
            self._apply_mass_target_effect(state, next_context)

    def _apply_mass_target_effect(self, state: GameState, context: PendingResponse) -> None:
        source = self._player_by_id(state, context.source_player_id or context.origin_player_id or "")
        target = self._player_by_id(state, context.target_player_id or "")
        if context.effect_type == "nanmanruqin":
            if any(card.name == "sha" for card in target.hand):
                state.phase = "response"
                state.pending_response = PendingResponse(
                    type="respond_sha",
                    player_id=target.id,
                    source_player_id=source.id,
                    origin_player_id=source.id,
                    target_player_id=target.id,
                    effect_type="nanmanruqin",
                    remaining_player_ids=context.remaining_player_ids,
                )
            else:
                self._damage(state, target, source, context)
        elif context.effect_type == "wanjianqifa":
            if self._bagua_success(state, source, target, effect_type="wanjianqifa"):
                self._event(state, f"{target.name} 的八卦阵判定成功，视为出闪")
                self._continue_mass_trick(state, context)
            elif any(card.name == "shan" for card in target.hand):
                state.phase = "response"
                state.pending_response = PendingResponse(
                    type="respond_shan",
                    player_id=target.id,
                    source_player_id=source.id,
                    origin_player_id=source.id,
                    target_player_id=target.id,
                    effect_type="wanjianqifa",
                    remaining_player_ids=context.remaining_player_ids,
                )
            else:
                self._damage(state, target, source, context)
        elif context.effect_type == "taoyuanjieyi":
            if target.hp < target.max_hp:
                target.hp += 1
                self._event(state, f"{target.name} 因桃园结义回复 1 点体力")
            self._continue_mass_trick(state, context)
        elif context.effect_type == "wugufengdeng":
            card = self._draw_one(state)
            if card:
                target.hand.append(card)
                target.hand_count = len(target.hand)
                self._event(state, f"{target.name} 因五谷丰登获得 1 张牌")
            self._continue_mass_trick(state, context)

    def _start_wugu(self, state: GameState, source: Player) -> None:
        ordered_ids = self._ordered_alive_ids(state, source.id)
        pool = [card for card in (self._draw_one(state) for _ in ordered_ids) if card]
        state.phase = "response"
        state.pending_response = PendingResponse(
            type="wugu",
            player_id=ordered_ids[0],
            source_player_id=source.id,
            origin_player_id=source.id,
            card_name="wugufengdeng",
            effect_type="wugufengdeng",
            remaining_player_ids=ordered_ids[1:],
            wugu_pool=pool,
        )
        self._event(state, f"五谷丰登亮出 {len(pool)} 张公共牌")

    def _choose_wugu_card(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None or pending.type != "wugu":
            raise ValueError("当前没有五谷丰登选牌")
        player = self._player_by_id(state, pending.player_id)
        pool = pending.wugu_pool or []
        chosen = next((card for card in pool if card.id == action.card_id), None)
        if chosen is None:
            raise ValueError("五谷丰登牌池中没有该牌")
        pool.remove(chosen)
        player.hand.append(chosen)
        player.hand_count = len(player.hand)
        self._event(state, f"{player.name} 从五谷丰登选择了 {CARD_LABELS[chosen.name]}")
        remaining = [player_id for player_id in (pending.remaining_player_ids or []) if self._player_by_id(state, player_id).alive]
        if remaining and pool:
            pending.player_id = remaining[0]
            pending.remaining_player_ids = remaining[1:]
            pending.wugu_pool = pool
            state.pending_response = pending
            state.phase = "response"
            return
        state.discard_pile.extend(pool)
        if pool:
            self._event(state, f"五谷丰登剩余 {len(pool)} 张牌进入弃牌堆")
        source = self._player_by_id(state, pending.origin_player_id or pending.source_player_id or player.id)
        state.current_player_index = self._index_by_id(state, source.id)
        state.pending_response = None
        state.phase = "play"

    def _request_shan(
        self,
        state: GameState,
        source: Player,
        target: Player,
        effect_type: str,
        remaining: list[str] | None = None,
        origin_player_id: str | None = None,
    ) -> None:
        if any(card.name == "shan" for card in target.hand):
            state.phase = "response"
            state.pending_response = PendingResponse(
                type="respond_shan",
                player_id=target.id,
                source_player_id=source.id,
                origin_player_id=origin_player_id or source.id,
                target_player_id=target.id,
                effect_type=effect_type,
                remaining_player_ids=remaining,
            )
        else:
            self._damage(
                state,
                target,
                source,
                PendingResponse(
                    type="respond_shan",
                    player_id=target.id,
                    source_player_id=source.id,
                    origin_player_id=origin_player_id or source.id,
                    target_player_id=target.id,
                    effect_type=effect_type,
                    remaining_player_ids=remaining,
                ),
            )

    def _respond_sha_failed(self, state: GameState, player: Player, source: Player, pending: PendingResponse) -> None:
        if pending.effect_type == "juedou":
            self._damage(state, player, source, pending)
        elif pending.effect_type == "nanmanruqin":
            self._damage(state, player, source, pending)
        elif pending.effect_type == "jiedaosharen":
            owner = self._player_by_id(state, pending.player_id)
            recipient = self._player_by_id(state, pending.origin_player_id or "")
            if owner.equipment.weapon:
                recipient.hand.append(owner.equipment.weapon)
                recipient.hand_count = len(recipient.hand)
                self._event(state, f"{owner.name} 未出杀，武器交给 {recipient.name}")
                owner.equipment.weapon = None
            self._finish_response_context(state, pending)

    def _damage(self, state: GameState, target: Player, source: Player | None, context: PendingResponse | None = None, amount: int = 1) -> None:
        if not target.alive:
            self._finish_response_context(state, context)
            return
        target.hp -= amount
        self._event(state, f"{target.name} 受到 {amount} 点伤害")
        if target.hp <= 0:
            self._start_dying(state, target, source, context)
        else:
            self._finish_response_context(state, context)

    def _start_dying(self, state: GameState, target: Player, source: Player | None, context: PendingResponse | None) -> None:
        queue = self._ordered_alive_ids(state, start_player_id=target.id)
        state.phase = "response"
        state.pending_response = PendingResponse(
            type="dying_tao",
            player_id=queue[0],
            source_player_id=source.id if source else None,
            origin_player_id=context.origin_player_id if context else (source.id if source else target.id),
            target_player_id=target.id,
            effect_type=context.effect_type if context else None,
            remaining_player_ids=context.remaining_player_ids if context else None,
            queue_player_ids=queue[1:],
        )
        self._event(state, f"{target.name} 进入濒死，开始求桃")

    def _dying_tao(self, state: GameState, action: Action) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有濒死响应")
        helper = self._player_by_id(state, pending.player_id)
        target = self._player_by_id(state, pending.target_player_id or pending.player_id)
        card = self._take_card(helper, action.card_id or "")
        state.discard_pile.append(card)
        target.hp += 1
        if target.hp <= 0:
            self._event(state, f"{helper.name} 对 {target.name} 使用桃，仍需继续求桃")
            pending.player_id = target.id
            pending.queue_player_ids = self._ordered_alive_ids(state, start_player_id=target.id)[1:]
            state.pending_response = pending
            state.phase = "response"
            return
        self._event(state, f"{helper.name} 使用桃使 {target.name} 脱离濒死")
        state.pending_response = None
        self._finish_response_context(state, pending)

    def _pass_dying_tao(self, state: GameState) -> None:
        pending = state.pending_response
        if pending is None:
            raise ValueError("当前没有濒死响应")
        player = self._player_by_id(state, pending.player_id)
        target = self._player_by_id(state, pending.target_player_id or pending.player_id)
        if any(card.name == "tao" for card in player.hand):
            self._event(state, f"{player.name} 选择不对 {target.name} 使用桃")
        else:
            self._event(state, f"{player.name} 没有桃可救 {target.name}")
        queue = pending.queue_player_ids or []
        if queue:
            pending.player_id = queue[0]
            pending.queue_player_ids = queue[1:]
            return
        source = self._player_by_id(state, pending.source_player_id) if pending.source_player_id else None
        target.alive = False
        target.hp = 0
        state.discard_pile.extend(target.hand)
        target.hand = []
        target.hand_count = 0
        self._discard_equipment_and_judgment(state, target)
        self._event(state, f"{target.name} 死亡")
        self._apply_death_rewards(state, target, source)
        state.pending_response = None
        self._check_winner(state)
        if not state.winner:
            self._finish_response_context(state, pending, fallback_player=source)

    def _finish_response_context(self, state: GameState, context: PendingResponse | None, fallback_player: Player | None = None) -> None:
        if context and context.remaining_player_ids and context.effect_type in {"nanmanruqin", "wanjianqifa", "taoyuanjieyi", "wugufengdeng"}:
            self._continue_mass_trick(state, context)
            return
        if context and context.effect_type == "shandian_judgment":
            actor = self._player_by_id(state, context.origin_player_id or context.player_id)
            state.current_player_index = self._index_by_id(state, actor.id)
            state.pending_response = None
            if actor.alive and not state.winner:
                state.phase = "draw"
                self._draw_cards(state, actor, 2)
                self._event(state, f"{actor.name} 摸了 2 张牌")
                state.phase = "play"
            return
        actor_id = context.origin_player_id or context.source_player_id if context else None
        if actor_id:
            state.current_player_index = self._index_by_id(state, actor_id)
        elif fallback_player:
            state.current_player_index = self._index_by_id(state, fallback_player.id)
        state.pending_response = None
        state.phase = "play"

    def _resolve_judgment_area(self, state: GameState, player: Player) -> None:
        for card in list(reversed(player.judgment_area)):
            player.judgment_area.remove(card)
            judge = self._judge(state)
            if card.name == "lebusishu":
                state.discard_pile.append(card)
                if judge.suit == "heart":
                    self._event(state, f"{player.name} 的乐不思蜀判定为红桃，出牌阶段不跳过")
                else:
                    self._event(state, f"{player.name} 的乐不思蜀判定未命中红桃，跳过出牌阶段")
                    state.phase = "draw"
                    self._draw_cards(state, player, 2)
                    self._event(state, f"{player.name} 摸了 2 张牌")
                    self._enter_discard_or_next(state)
                    return
            elif card.name == "shandian":
                if judge.suit == "spade" and judge.rank in {"2", "3", "4", "5", "6", "7", "8", "9"}:
                    state.discard_pile.append(card)
                    self._event(state, f"{player.name} 的闪电判定命中，受到 3 点雷电伤害")
                    player.hp -= 3
                    self._event(state, f"{player.name} 受到 3 点伤害")
                    if player.hp <= 0:
                        self._start_dying(
                            state,
                            player,
                            None,
                            PendingResponse(type="respond_shan", player_id=player.id, origin_player_id=player.id, effect_type="shandian_judgment"),
                        )
                        return
                    continue
                next_player = self._next_player_without_delayed_trick(state, player, "shandian")
                if next_player:
                    next_player.judgment_area.append(card)
                    self._event(state, f"{player.name} 的闪电未命中，移动给 {next_player.name}")
                else:
                    state.discard_pile.append(card)
                    self._event(state, f"{player.name} 的闪电未命中，但无人可接收，进入弃牌堆")

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
        discarded = 0
        for card_id in action.target_card_ids or []:
            state.discard_pile.append(self._take_card(player, card_id))
            discarded += 1
        self._event(state, f"{player.name} 弃置了 {discarded} 张牌")
        state.pending_response = None
        self._advance_to_next_player(state)
        self.start_turn(state)

    def _check_winner(self, state: GameState) -> None:
        if state.winner:
            return
        lord = next(player for player in state.players if player.role == "zhu")
        if not lord.alive:
            alive = [player for player in state.players if player.alive]
            state.winner = "nei" if len(alive) == 1 and alive[0].role == "nei" else "fan"
            state.phase = "game_over"
            state.pending_response = None
            self._event(state, "主公死亡，内奸胜利" if state.winner == "nei" else "主公死亡，反贼胜利")
            return
        rebels_alive = any(player.alive and player.role == "fan" for player in state.players)
        spy_alive = any(player.alive and player.role == "nei" for player in state.players)
        if not rebels_alive and not spy_alive:
            state.winner = "zhu"
            state.phase = "game_over"
            state.pending_response = None
            self._event(state, "所有反贼和内奸死亡，主公阵营胜利")

    def _actor_waiting_for_action(self, state: GameState) -> Player | None:
        if state.winner:
            return None
        if state.pending_response:
            return self._player_by_id(state, state.pending_response.player_id)
        if state.phase == "play":
            return self.current_player(state)
        return None

    def _default_action_id(self, legal: list[Action]) -> str:
        for preferred in ("dying_tao", "respond_shan", "respond_sha", "wuxie", "wugu_choose", "pass_response", "end_phase"):
            match = next((action for action in legal if action.type == preferred or action.action_id == preferred), None)
            if match:
                return match.action_id
        for action in legal:
            if action.type == "discard_cards":
                return action.action_id
        return legal[0].action_id

    def _ai_action_allowed_by_role(self, state: GameState, actor: Player, action: Action) -> bool:
        if action.type != "play_card" or action.card_name not in {"sha", "juedou", "nanmanruqin", "wanjianqifa"}:
            return True
        target_ids = []
        if action.target_player_id:
            target_ids.append(action.target_player_id)
        if action.card_name in {"nanmanruqin", "wanjianqifa"}:
            target_ids = [target.id for target in self._alive_opponents(state, actor)]
        if actor.role == "zhong":
            return not any(self._player_by_id(state, target_id).role == "zhu" for target_id in target_ids)
        return True

    def _ai_ranked_actions(self, state: GameState, actor: Player, actions: list[Action]) -> list[Action]:
        if state.pending_response:
            if state.pending_response.type == "respond_shan":
                return [action for action in actions if action.type == "respond_shan"] or actions
            if state.pending_response.type == "respond_sha":
                return [action for action in actions if action.type == "respond_sha"] or actions
            if state.pending_response.type == "dying_tao":
                preferred_type = "dying_tao" if self._ai_should_use_tao_for_dying(state, actor, state.pending_response) else "pass_response"
                return [action for action in actions if action.type == preferred_type] or actions
            if state.pending_response.type == "wuxie":
                preferred_type = "wuxie" if self._ai_should_use_wuxie(state, actor, state.pending_response) else "pass_response"
                return [action for action in actions if action.type == preferred_type] or actions
            if state.pending_response.type == "wugu":
                return sorted(actions, key=lambda action: self._ai_wugu_card_score(action), reverse=True) or actions
            return actions

        scored = sorted(actions, key=lambda action: self._ai_action_score(state, actor, action), reverse=True)
        best_score = self._ai_action_score(state, actor, scored[0]) if scored else 0
        if best_score > 0:
            return [action for action in scored if self._ai_action_score(state, actor, action) == best_score]
        return scored or actions

    def _ai_action_score(self, state: GameState, actor: Player, action: Action) -> int:
        if action.type == "end_phase":
            return 0
        if action.type == "equip_card":
            return 52
        if action.type != "play_card":
            return 20

        card_name = action.card_name
        if card_name == "tao":
            return 95 if actor.hp <= 2 else 65
        if card_name == "sha":
            return 100 + self._ai_target_score(state, actor, action.target_player_id)
        if card_name == "juedou":
            return 82 + self._ai_target_score(state, actor, action.target_player_id)
        if card_name in {"guohechaiqiao", "shunshouqianyang"}:
            return 86 + self._ai_target_score(state, actor, action.target_player_id)
        if card_name == "jiedaosharen":
            return 78 + self._ai_target_score(state, actor, action.secondary_target_player_id)
        if card_name in {"nanmanruqin", "wanjianqifa"}:
            return 68 if self._ai_mass_attack_is_reasonable(state, actor) else 24
        if card_name == "wuzhongshengyou":
            return 62
        if card_name == "lebusishu":
            return 84 + self._ai_target_score(state, actor, action.target_player_id)
        if card_name == "shandian":
            return 30
        if card_name == "wugufengdeng":
            return 42
        if card_name == "taoyuanjieyi":
            return 35 if actor.hp < actor.max_hp else 18
        return 10

    def _ai_wugu_card_score(self, action: Action) -> int:
        priorities = {
            "tao": 90,
            "sha": 82,
            "wuxiekeji": 78,
            "shan": 72,
            "juedou": 70,
            "guohechaiqiao": 68,
            "shunshouqianyang": 68,
            "lebusishu": 64,
            "nanmanruqin": 58,
            "wanjianqifa": 58,
            "wuzhongshengyou": 56,
        }
        if action.card_name in EQUIPMENT_CARDS:
            return 60
        return priorities.get(action.card_name, 20)

    def _ai_target_score(self, state: GameState, actor: Player, target_player_id: str | None) -> int:
        if not target_player_id:
            return 0
        target = self._player_by_id(state, target_player_id)
        score = max(0, target.max_hp - target.hp) + max(0, 5 - target.hp)
        if actor.role == "fan":
            if target.role_public and target.role == "zhu":
                return score + 80
            if target.role == "fan":
                return score - 60
            return score + 20
        if actor.role in {"zhu", "zhong"}:
            if target.role == "fan":
                return score + 60
            if target.role == "zhu":
                return score - 100
            return score + 10
        if actor.role == "nei":
            if target.hp <= 2:
                return score + 35
            return score + 5
        return score

    def _ai_mass_attack_is_reasonable(self, state: GameState, actor: Player) -> bool:
        targets = self._alive_opponents(state, actor)
        if actor.role == "fan":
            return any(target.role_public and target.role == "zhu" for target in targets)
        if actor.role == "zhong":
            return not any(target.role == "zhu" for target in targets)
        return True

    def _ai_should_use_wuxie(self, state: GameState, actor: Player, pending: PendingResponse) -> bool:
        effect = pending.effect_type or pending.card_name
        source = self._player_by_id(state, pending.source_player_id or pending.origin_player_id or "")
        target = self._player_by_id(state, pending.target_player_id) if pending.target_player_id else source
        beneficial = self._is_beneficial_effect(pending)
        harmful = effect in {
            "guohechaiqiao",
            "shunshouqianyang",
            "jiedaosharen",
            "nanmanruqin",
            "wanjianqifa",
            "juedou",
            "lebusishu",
            "shandian",
        }

        if pending.wuxie_effect_cancelled:
            if self._same_camp(actor, source) and beneficial:
                return True
            if self._same_camp(actor, target) and harmful:
                return True
            if actor.role == "fan" and source.role_public and source.role == "zhu" and harmful:
                return False
            if actor.role in {"zhu", "zhong"} and target.role == "fan" and harmful:
                return False

        if actor.role == "fan":
            if target.role_public and target.role == "zhu" and beneficial:
                return True
            if source.role_public and source.role == "zhu" and effect in {"wuzhongshengyou", "wugufengdeng", "taoyuanjieyi"}:
                return True
            if target.role == "fan" and harmful:
                return True
            return False

        if actor.role == "zhong":
            if target.role == "zhu" and harmful:
                return True
            if target.role == "zhu" and beneficial:
                return False
            if source.role == "zhu" and beneficial:
                return False
            return target.role == "fan" and beneficial

        if actor.role == "zhu":
            if beneficial and target.id == actor.id:
                return False
            if harmful and target.id == actor.id:
                return True
            return target.role == "fan" and beneficial

        if actor.role == "nei":
            if target.id == actor.id and harmful:
                return True
            if target.id == actor.id and beneficial:
                return False
            return target.hp <= 2 and beneficial

        return False

    def _same_camp(self, actor: Player, target: Player) -> bool:
        if actor.id == target.id:
            return True
        if actor.role == "fan":
            return target.role == "fan"
        if actor.role in {"zhu", "zhong"}:
            return target.role in {"zhu", "zhong"}
        return target.role == "nei"

    def _ai_should_use_tao_for_dying(self, state: GameState, actor: Player, pending: PendingResponse) -> bool:
        if not any(card.name == "tao" for card in actor.hand):
            return False
        target = self._player_by_id(state, pending.target_player_id or pending.player_id)
        if target.id == actor.id:
            return True
        if actor.role == "fan":
            return target.role == "fan"
        if actor.role == "zhong":
            return target.role in {"zhu", "zhong"}
        if actor.role == "zhu":
            return target.role in {"zhu", "zhong"}
        if actor.role == "nei":
            lord = next(player for player in state.players if player.role == "zhu")
            rebels_alive = sum(1 for player in state.players if player.alive and player.role == "fan")
            if target.role == "zhu" and rebels_alive > 0:
                return True
            return target.role == "nei"
        return False

    def _wuxie_waiting_message(self, state: GameState, context: PendingResponse) -> str:
        responder = self._player_by_id(state, context.player_id).name if context.player_id else "无人"
        target = self._player_by_id(state, context.target_player_id).name if context.target_player_id else "所有目标"
        source = self._player_by_id(state, context.source_player_id or context.origin_player_id or "").name
        return f"{CARD_LABELS[context.card_name]}等待无懈可击响应：响应者 {responder}，目标 {target}，来源 {source}"

    def _card_action(
        self,
        action_id: str,
        action_type: str,
        card: Card,
        target: Player | None,
        label: str,
        secondary_target: Player | None = None,
        selected_area: str | None = None,
        selected_card: Card | None = None,
    ) -> Action:
        return Action(
            action_id=action_id,
            type=action_type,
            card_id=card.id,
            card_name=card.name,
            card_suit=card.suit,
            card_rank=card.rank,
            target_player_id=target.id if target else None,
            target_player_name=target.name if target else None,
            secondary_target_player_id=secondary_target.id if secondary_target else None,
            secondary_target_player_name=secondary_target.name if secondary_target else None,
            selected_area=selected_area,
            selected_card_id=selected_card.id if selected_card else None,
            selected_card_name=selected_card.name if selected_card else None,
            selected_card_suit=selected_card.suit if selected_card else None,
            selected_card_rank=selected_card.rank if selected_card else None,
            label=label,
        )

    def _area_target_actions(self, card: Card, target: Player, effect: CardName) -> list[Action]:
        prefix = "play_guohechaiqiao" if effect == "guohechaiqiao" else "play_shunshouqianyang"
        effect_label = CARD_LABELS[effect]
        actions: list[Action] = []
        if target.hand:
            actions.append(
                self._card_action(
                    f"{prefix}:{card.id}:{target.id}:hand:random",
                    "play_card",
                    card,
                    target,
                    f"{effect_label} → {target.name} 的随机手牌",
                    selected_area="hand",
                )
            )
        for slot, slot_label in (("weapon", "武器区"), ("armor", "防具区"), ("attack_horse", "-1马"), ("defense_horse", "+1马")):
            selected = getattr(target.equipment, slot)
            if selected:
                actions.append(
                    self._card_action(
                        f"{prefix}:{card.id}:{target.id}:equipment:{selected.id}",
                        "play_card",
                        card,
                        target,
                        f"{effect_label} → {target.name} 的{slot_label}：{CARD_LABELS[selected.name]}",
                        selected_area="equipment",
                        selected_card=selected,
                    )
                )
        for selected in target.judgment_area:
            actions.append(
                self._card_action(
                    f"{prefix}:{card.id}:{target.id}:judgment:{selected.id}",
                    "play_card",
                    card,
                    target,
                    f"{effect_label} → {target.name} 的判定区：{CARD_LABELS[selected.name]}",
                    selected_area="judgment",
                    selected_card=selected,
                )
            )
        return actions

    def _card_brief(self, card: Card) -> str:
        return f"{CARD_LABELS[card.name]}({card.suit} {card.rank})"

    def _can_use_sha(self, player: Player) -> bool:
        return not player.used_sha_this_turn or bool(player.equipment.weapon and player.equipment.weapon.name == "zhugeliannu")

    def _in_attack_range(self, state: GameState, source: Player, target: Player) -> bool:
        return in_attack_range(state.players, source, target)

    def _attack_range(self, player: Player) -> int:
        return attack_range(player)

    def _distance(self, state: GameState, source: Player, target: Player) -> int:
        return distance_between(state.players, source, target)

    def _armor_blocks_sha(self, state: GameState, source: Player, target: Player, card: Card) -> bool:
        del state
        if source.equipment.weapon and source.equipment.weapon.name == "qinggangjian":
            return False
        return bool(target.equipment.armor and target.equipment.armor.name == "renwangdun" and card.suit in BLACK_SUITS)

    def _bagua_success(self, state: GameState, source: Player, target: Player, effect_type: str) -> bool:
        if effect_type == "sha" and source.equipment.weapon and source.equipment.weapon.name == "qinggangjian":
            return False
        if not target.equipment.armor or target.equipment.armor.name != "baguazhen":
            return False
        judge = self._judge(state)
        return judge.suit in RED_SUITS

    def _judge(self, state: GameState) -> Card:
        card = self._draw_one(state)
        if card is None:
            raise ValueError("牌堆和弃牌堆均为空，无法判定")
        state.discard_pile.append(card)
        self._event(state, f"判定牌为 {CARD_LABELS[card.name]} {card.suit} {card.rank}")
        return card

    def _wuxie_queue(self, state: GameState, context: PendingResponse | None = None) -> list[str]:
        excluded_ids: set[str] = set()
        if context:
            source_id = context.origin_player_id or context.source_player_id
            if source_id:
                excluded_ids.add(source_id)
            if self._is_beneficial_effect(context) and context.target_player_id:
                excluded_ids.add(context.target_player_id)
        return [
            player.id
            for player in state.players
            if player.alive
            and player.id not in excluded_ids
            and any(card.name == "wuxiekeji" for card in player.hand)
        ]

    def _wuxie_counter_queue(self, state: GameState, last_responder_id: str) -> list[str]:
        return [
            player.id
            for player in state.players
            if player.alive
            and player.id != last_responder_id
            and any(card.name == "wuxiekeji" for card in player.hand)
        ]

    def _is_beneficial_effect(self, context: PendingResponse) -> bool:
        return (context.effect_type or context.card_name) in {"wuzhongshengyou", "taoyuanjieyi", "wugufengdeng"}

    def _alive_opponents(self, state: GameState, player: Player) -> list[Player]:
        return [target for target in state.players if target.alive and target.id != player.id]

    def _ordered_alive_ids(self, state: GameState, start_player_id: str) -> list[str]:
        start = self._index_by_id(state, start_player_id)
        ordered = []
        for offset in range(len(state.players)):
            player = state.players[(start + offset) % len(state.players)]
            if player.alive:
                ordered.append(player.id)
        return ordered

    def _next_alive_player(self, state: GameState, player: Player) -> Player:
        start = self._index_by_id(state, player.id)
        for offset in range(1, len(state.players) + 1):
            candidate = state.players[(start + offset) % len(state.players)]
            if candidate.alive:
                return candidate
        return player

    def _next_player_without_delayed_trick(self, state: GameState, player: Player, card_name: CardName) -> Player | None:
        start = self._index_by_id(state, player.id)
        for offset in range(1, len(state.players) + 1):
            candidate = state.players[(start + offset) % len(state.players)]
            if candidate.alive and not self._has_delayed_trick(candidate, card_name):
                return candidate
        return None

    def _has_any_card(self, player: Player) -> bool:
        return bool(player.hand or player.equipment.weapon or player.equipment.armor or player.equipment.attack_horse or player.equipment.defense_horse or player.judgment_area)

    def _has_delayed_trick(self, player: Player, card_name: CardName) -> bool:
        return any(card.name == card_name for card in player.judgment_area)

    def _remove_random_card_from_area(self, player: Player) -> Card:
        areas: list[tuple[str, Card]] = []
        areas.extend(("hand", card) for card in player.hand)
        for slot in ("weapon", "armor", "attack_horse", "defense_horse"):
            card = getattr(player.equipment, slot)
            if card:
                areas.append((slot, card))
        areas.extend(("judgment", card) for card in player.judgment_area)
        if not areas:
            raise ValueError("目标没有可操作的牌")
        area, card = random.choice(areas)
        if area == "hand":
            player.hand.remove(card)
            player.hand_count = len(player.hand)
        elif area == "judgment":
            player.judgment_area.remove(card)
        else:
            setattr(player.equipment, area, None)
        return card

    def _remove_selected_card_from_area(self, player: Player, selected_area: str | None, selected_card_id: str | None) -> Card:
        if selected_area == "hand":
            if not player.hand:
                raise ValueError("目标没有手牌")
            index = random.randrange(len(player.hand))
            card = player.hand.pop(index)
            player.hand_count = len(player.hand)
            return card
        if selected_area == "equipment":
            if not selected_card_id:
                raise ValueError("选择装备区牌时必须提供 selected_card_id")
            for slot in ("weapon", "armor", "attack_horse", "defense_horse"):
                card = getattr(player.equipment, slot)
                if card and card.id == selected_card_id:
                    setattr(player.equipment, slot, None)
                    return card
            raise ValueError("目标装备区没有指定牌")
        if selected_area == "judgment":
            if not selected_card_id:
                raise ValueError("选择判定区牌时必须提供 selected_card_id")
            for index, card in enumerate(player.judgment_area):
                if card.id == selected_card_id:
                    return player.judgment_area.pop(index)
            raise ValueError("目标判定区没有指定牌")
        raise ValueError("缺少可操作区域")

    def _area_label(self, selected_area: str | None) -> str:
        if selected_area == "hand":
            return "随机手牌"
        if selected_area == "equipment":
            return "装备区"
        if selected_area == "judgment":
            return "判定区"
        return "区域牌"

    def _discard_equipment_and_judgment(self, state: GameState, player: Player) -> None:
        for slot in ("weapon", "armor", "attack_horse", "defense_horse"):
            card = getattr(player.equipment, slot)
            if card:
                state.discard_pile.append(card)
                setattr(player.equipment, slot, None)
        state.discard_pile.extend(player.judgment_area)
        player.judgment_area = []

    def _apply_death_rewards(self, state: GameState, dead: Player, source: Player | None) -> None:
        if source is None or not source.alive:
            return
        if dead.role == "fan":
            self._draw_cards(state, source, 3)
            self._event(state, f"{source.name} 击杀反贼 {dead.name}，摸 3 张牌")
        if source.role == "zhu" and dead.role == "zhong":
            discarded = len(source.hand)
            state.discard_pile.extend(source.hand)
            source.hand = []
            source.hand_count = 0
            for slot in ("weapon", "armor", "attack_horse", "defense_horse"):
                card = getattr(source.equipment, slot)
                if card:
                    state.discard_pile.append(card)
                    discarded += 1
                    setattr(source.equipment, slot, None)
            self._event(state, f"{source.name} 误杀忠臣 {dead.name}，弃置所有手牌和装备，共 {discarded} 张")

    def _discard_name_combinations(self, player: Player, required: int) -> list[tuple[CardName, ...]]:
        counts = Counter(card.name for card in player.hand)
        names = sorted(counts, key=lambda name: CARD_LABELS[name])
        results: list[tuple[CardName, ...]] = []

        def visit(index: int, remaining: int, current: list[CardName]) -> None:
            if index == len(names):
                if remaining == 0:
                    results.append(tuple(current))
                return
            name = names[index]
            max_count = min(counts[name], remaining)
            for count in range(max_count + 1):
                current.extend([name] * count)
                visit(index + 1, remaining - count, current)
                if count:
                    del current[-count:]

        visit(0, required, [])
        return results

    def _advance_to_next_player(self, state: GameState) -> None:
        previous = state.current_player_index
        for offset in range(1, len(state.players) + 1):
            candidate = (previous + offset) % len(state.players)
            if state.players[candidate].alive:
                state.current_player_index = candidate
                if candidate <= previous:
                    state.round += 1
                return

    def _draw_cards(self, state: GameState, player: Player, count: int) -> None:
        for _ in range(count):
            card = self._draw_one(state)
            if card:
                player.hand.append(card)
        player.hand_count = len(player.hand)

    def _draw_one(self, state: GameState) -> Card | None:
        if not state.deck:
            self._reshuffle_discard(state)
        if not state.deck:
            return None
        return state.deck.pop(0)

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

    def _take_random_card_by_name(self, player: Player, card_name: CardName | None) -> Card:
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

    def _index_by_id(self, state: GameState, player_id: str) -> int:
        for index, player in enumerate(state.players):
            if player.id == player_id:
                return index
        raise ValueError("找不到指定玩家")

    def _event(self, state: GameState, message: str) -> None:
        state.recent_events.append(message)
        state.recent_events = state.recent_events[-30:]
        game_events.publish_state(state)
