from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.game.engine import GameEngine
from app.game.state import public_state_for_human
from app.llm.prompt import compact_prompt
from app.main import app
from app.models import AIConfig, Action, Card, CreateGameRequest, PendingResponse


def make_game(seed: int = 1):
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2")],
            seed=seed,
        )
    )
    return engine, state


def force_human_play(engine: GameEngine, state):
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    state.players[0].alive = True
    engine.refresh_legal_actions(state)


def action_id(
    engine: GameEngine,
    state,
    *,
    card_name: str | None = None,
    action_type: str | None = None,
    target_id: str | None = None,
    secondary_target_id: str | None = None,
    selected_area: str | None = None,
    selected_card_id: str | None = None,
) -> str:
    for action in engine.refresh_legal_actions(state):
        if card_name is not None and action.card_name != card_name:
            continue
        if action_type is not None and action.type != action_type:
            continue
        if target_id is not None and action.target_player_id != target_id:
            continue
        if secondary_target_id is not None and action.secondary_target_player_id != secondary_target_id:
            continue
        if selected_area is not None and action.selected_area != selected_area:
            continue
        if selected_card_id is not None and action.selected_card_id != selected_card_id:
            continue
        return action.action_id
    raise AssertionError("未找到指定合法动作")


def test_create_game_success():
    _, state = make_game()
    assert state.game_id
    assert len(state.players) == 3
    assert any(player.role == "zhu" for player in state.players)


def test_initial_hand_count():
    _, state = make_game()
    for index, player in enumerate(state.players):
        expected = 6 if index == state.current_player_index else 4
        assert len(player.hand) == expected


def test_deck_order_is_not_fixed_between_games():
    _, first = make_game(seed=1)
    _, second = make_game(seed=2)
    assert [card.id for card in first.deck[:10]] != [card.id for card in second.deck[:10]]


def test_v02_deck_has_standard_card_count():
    _, state = make_game(seed=1)
    all_cards = state.deck + state.discard_pile + [card for player in state.players for card in player.hand]
    assert len(all_cards) == 108
    assert {"wuxiekeji", "nanmanruqin", "wanjianqifa", "lebusishu", "shandian"} <= {card.name for card in all_cards}


def test_legal_actions_not_empty_for_play_phase():
    engine, state = make_game()
    force_human_play(engine, state)
    actions = engine.legal_actions(state)
    assert actions


def test_sha_only_in_play_phase():
    engine, state = make_game()
    force_human_play(engine, state)
    play_actions = engine.legal_actions(state)
    assert any(action.card_name == "sha" for action in play_actions) or any(
        card.name != "sha" for card in state.players[0].hand
    )
    state.phase = "discard"
    state.pending_response = None
    assert not any(action.card_name == "sha" for action in engine.legal_actions(state))


def test_tao_only_when_damaged():
    engine, state = make_game()
    force_human_play(engine, state)
    human = state.players[0]
    human.hand = [Card(id="test-tao", name="tao", suit="heart", rank="9")]
    human.hand_count = 1
    state.players[1].hp = state.players[1].max_hp - 1
    human.hp = human.max_hp
    assert not any(action.card_name == "tao" for action in engine.legal_actions(state))
    human.hp = human.max_hp - 1
    tao_actions = [action for action in engine.legal_actions(state) if action.card_name == "tao"]
    assert [action.action_id for action in tao_actions] == [f"play_tao:test-tao:{human.id}"]


def test_duplicate_card_actions_are_grouped():
    engine, state = make_game()
    force_human_play(engine, state)
    human = state.players[0]
    human.hand = [
        Card(id="test-sha-1", name="sha", suit="spade", rank="7"),
        Card(id="test-sha-2", name="sha", suit="heart", rank="8"),
        Card(id="test-tao-1", name="tao", suit="heart", rank="9"),
        Card(id="test-tao-2", name="tao", suit="diamond", rank="10"),
    ]
    human.hp = human.max_hp - 1

    actions = engine.legal_actions(state)
    sha_actions = [action for action in actions if action.card_name == "sha"]
    tao_actions = [action for action in actions if action.card_name == "tao"]

    alive_targets = [player for player in state.players if player.alive and player.id != human.id]
    assert len(sha_actions) == len(alive_targets) * 2
    assert {action.card_id for action in sha_actions} == {"test-sha-1", "test-sha-2"}
    assert len(tao_actions) == 2
    assert {action.card_id for action in tao_actions} == {"test-tao-1", "test-tao-2"}
    assert {action.target_player_id for action in tao_actions} == {human.id}


def test_play_phase_tao_cannot_heal_other_player_even_if_forged():
    engine, state = make_game()
    force_human_play(engine, state)
    human, target = state.players[0], state.players[1]
    human.hand = [Card(id="test-tao", name="tao", suit="heart", rank="9")]
    human.hand_count = 1
    human.hp = human.max_hp - 1
    target.hp = target.max_hp - 1

    with pytest.raises(ValueError, match="出牌阶段桃只能对自己使用"):
        engine._play_tao(  # noqa: SLF001 - 验证绕过 legal_actions 的防御性校验
            state,
            Action(
                action_id=f"play_tao:test-tao:{target.id}",
                type="play_card",
                card_id="test-tao",
                card_name="tao",
                target_player_id=target.id,
                label="伪造桃",
            ),
        )
    assert target.hp == target.max_hp - 1


def test_v02_extended_cards_generate_legal_actions():
    engine, state = make_game()
    force_human_play(engine, state)
    human = state.players[0]
    human.hand = [
        Card(id="test-nanman", name="nanmanruqin", suit="spade", rank="K"),
        Card(id="test-wuzhong", name="wuzhongshengyou", suit="heart", rank="7"),
        Card(id="test-zhuge", name="zhugeliannu", suit="club", rank="A"),
    ]
    human.hand_count = len(human.hand)

    actions = engine.legal_actions(state)
    assert any(action.card_name == "nanmanruqin" for action in actions)
    assert any(action.card_name == "wuzhongshengyou" for action in actions)
    assert any(action.card_name == "zhugeliannu" and action.type == "equip_card" for action in actions)


def test_wuxiekeji_can_cancel_trick_effect():
    engine, state = make_game()
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    human, responder = state.players[0], state.players[1]
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    human.hand = [Card(id="test-wuzhong", name="wuzhongshengyou", suit="heart", rank="7")]
    human.hand_count = 1
    responder.hand = [Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q")]
    responder.hand_count = 1

    engine.execute_action(state, action_id(engine, state, card_name="wuzhongshengyou"))
    assert state.pending_response is not None
    assert state.pending_response.type == "wuxie"
    engine.execute_action(state, action_id(engine, state, action_type="wuxie"))
    assert len(human.hand) == 0
    assert state.phase == "play"


def test_wuxiekeji_does_not_prompt_source_to_cancel_own_wuzhongshengyou():
    engine, state = make_game()
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    human = state.players[0]
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    human.hand = [
        Card(id="test-wuzhong", name="wuzhongshengyou", suit="heart", rank="7"),
        Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q"),
    ]
    human.hand_count = 2

    engine.execute_action(state, action_id(engine, state, card_name="wuzhongshengyou"))
    assert state.pending_response is None
    assert len(human.hand) == 3


def test_wuxie_ai_legal_keeps_wuxie_and_pass_for_lord_benefit():
    engine, state = make_game()
    lord = next(player for player in state.players if player.role == "zhu")
    rebel = next(player for player in state.players if player.role == "fan")
    state.phase = "response"
    state.pending_response = PendingResponse(
        type="wuxie",
        player_id=rebel.id,
        source_player_id=lord.id,
        origin_player_id=lord.id,
        target_player_id=lord.id,
        card_name="wuzhongshengyou",
        effect_type="wuzhongshengyou",
    )
    rebel.hand = [Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q")]
    rebel.hand_count = 1

    ai_legal = engine.ai_legal_actions(state, rebel, engine.refresh_legal_actions(state))
    assert {action.type for action in ai_legal} == {"wuxie", "pass_response"}
    assert ai_legal[0].type == "wuxie"


def test_dying_tao_ai_legal_keeps_tao_and_pass_for_hidden_target():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    rebel = state.players[2]
    hidden_target = state.players[3]
    assert rebel.role == "fan"
    assert hidden_target.role == "fan"
    rebel.hand = [Card(id="test-tao", name="tao", suit="heart", rank="3")]
    rebel.hand_count = 1
    hidden_target.hp = 0
    state.phase = "response"
    state.pending_response = PendingResponse(
        type="dying_tao",
        player_id=rebel.id,
        source_player_id=state.players[0].id,
        target_player_id=hidden_target.id,
    )

    ai_legal = engine.ai_legal_actions(state, rebel, engine.refresh_legal_actions(state))
    assert {action.type for action in ai_legal} == {"dying_tao", "pass_response"}


def test_dying_tao_ai_legal_keeps_tao_and_pass_for_lord_target():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    lord = state.players[0]
    rebel = state.players[2]
    assert lord.role == "zhu"
    assert rebel.role == "fan"
    rebel.hand = [Card(id="test-tao", name="tao", suit="heart", rank="3")]
    rebel.hand_count = 1
    lord.hp = 0
    state.phase = "response"
    state.pending_response = PendingResponse(
        type="dying_tao",
        player_id=rebel.id,
        source_player_id=rebel.id,
        target_player_id=lord.id,
    )

    ai_legal = engine.ai_legal_actions(state, rebel, engine.refresh_legal_actions(state))
    assert {action.type for action in ai_legal} == {"dying_tao", "pass_response"}


def test_dying_tao_ai_legal_keeps_tao_and_pass_for_loyalist_saving_lord():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    lord = state.players[0]
    loyalist = state.players[1]
    assert lord.role == "zhu"
    assert loyalist.role == "zhong"
    loyalist.hand = [Card(id="test-tao", name="tao", suit="heart", rank="3")]
    loyalist.hand_count = 1
    lord.hp = 0
    state.phase = "response"
    state.pending_response = PendingResponse(
        type="dying_tao",
        player_id=loyalist.id,
        source_player_id=state.players[2].id,
        target_player_id=lord.id,
    )

    ai_legal = engine.ai_legal_actions(state, loyalist, engine.refresh_legal_actions(state))
    assert {action.type for action in ai_legal} == {"dying_tao", "pass_response"}


def test_dying_tao_fallback_self_saves_but_other_target_passes():
    engine, state = make_game()
    actor, other = state.players[1], state.players[2]
    actor.hand = [Card(id="test-tao", name="tao", suit="heart", rank="3")]
    actor.hand_count = 1
    state.phase = "response"
    state.pending_response = PendingResponse(type="dying_tao", player_id=actor.id, target_player_id=actor.id)
    legal = engine.refresh_legal_actions(state)
    assert engine._default_action_id(legal, state, actor) == "dying_tao:test-tao"  # noqa: SLF001

    state.pending_response = PendingResponse(type="dying_tao", player_id=actor.id, target_player_id=other.id)
    legal = engine.refresh_legal_actions(state)
    assert engine._default_action_id(legal, state, actor) == "pass_response"  # noqa: SLF001


def test_wuxie_fallback_defaults_to_pass_for_non_self_target():
    engine, state = make_game()
    actor, source, target = state.players[1], state.players[0], state.players[2]
    actor.hand = [Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q")]
    actor.hand_count = 1
    state.phase = "response"
    state.pending_response = PendingResponse(
        type="wuxie",
        player_id=actor.id,
        source_player_id=source.id,
        target_player_id=target.id,
        card_name="guohechaiqiao",
        effect_type="guohechaiqiao",
    )

    legal = engine.refresh_legal_actions(state)
    assert {action.type for action in legal} == {"wuxie", "pass_response"}
    assert engine._default_action_id(legal, state, actor) == "pass_response"  # noqa: SLF001


def test_wuxie_waiting_log_names_responder_target_and_source():
    engine, state = make_game()
    lord = next(player for player in state.players if player.role == "zhu")
    responder = next(player for player in state.players if player.id != lord.id)
    state.current_player_index = state.players.index(lord)
    state.phase = "play"
    state.pending_response = None
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    lord.hand = [Card(id="test-wuzhong", name="wuzhongshengyou", suit="heart", rank="7")]
    lord.hand_count = 1
    responder.hand = [Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q")]
    responder.hand_count = 1

    engine.execute_action(state, action_id(engine, state, card_name="wuzhongshengyou"))
    assert state.pending_response is not None
    assert any("响应者" in event and "目标" in event and "来源" in event for event in state.recent_events)


def test_juedou_requires_sha_response_when_target_has_sha():
    engine, state = make_game()
    source, target = state.players[0], state.players[1]
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    source.hand = [Card(id="test-juedou", name="juedou", suit="diamond", rank="A")]
    source.hand_count = 1
    target.hand = [Card(id="test-sha", name="sha", suit="spade", rank="7")]
    target.hand_count = 1

    engine.execute_action(state, action_id(engine, state, card_name="juedou", target_id=target.id))
    assert state.pending_response is not None
    assert state.pending_response.type == "respond_sha"
    assert state.pending_response.player_id == target.id
    action_ids = [action.action_id for action in engine.refresh_legal_actions(state)]
    assert any(item.startswith("respond_sha:") for item in action_ids)


def test_juedou_asks_wuxie_before_sha_response():
    engine, state = make_game()
    source, target = state.players[0], state.players[1]
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    source.hand = [Card(id="test-juedou", name="juedou", suit="diamond", rank="A")]
    source.hand_count = 1
    target.hand = [
        Card(id="test-sha", name="sha", suit="spade", rank="7"),
        Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q"),
    ]
    target.hand_count = 2

    engine.execute_action(state, action_id(engine, state, card_name="juedou", target_id=target.id))
    assert state.pending_response is not None
    assert state.pending_response.type == "wuxie"
    assert [action.type for action in engine.refresh_legal_actions(state)] == ["wuxie", "pass_response"]

    engine.execute_action(state, "pass_response")
    assert state.pending_response is not None
    assert state.pending_response.type == "respond_sha"
    assert any(action.type == "respond_sha" for action in engine.refresh_legal_actions(state))


def test_nanman_asks_wuxie_before_sha_response():
    engine, state = make_game()
    source, target = state.players[0], state.players[1]
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    source.hand = [Card(id="test-nanman", name="nanmanruqin", suit="spade", rank="K")]
    source.hand_count = 1
    target.hand = [
        Card(id="test-sha", name="sha", suit="spade", rank="7"),
        Card(id="test-wuxie", name="wuxiekeji", suit="club", rank="Q"),
    ]
    target.hand_count = 2

    engine.execute_action(state, action_id(engine, state, card_name="nanmanruqin"))
    assert state.pending_response is not None
    assert state.pending_response.type == "wuxie"
    assert [action.type for action in engine.refresh_legal_actions(state)] == ["wuxie", "pass_response"]

    engine.execute_action(state, "pass_response")
    assert state.pending_response is not None
    assert state.pending_response.type == "respond_sha"
    assert any(action.type == "respond_sha" for action in engine.refresh_legal_actions(state))


def test_juedou_target_without_sha_can_only_pass_response():
    engine, state = make_game()
    source, target = state.players[0], state.players[1]
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    source.hand = [Card(id="test-juedou", name="juedou", suit="diamond", rank="A")]
    source.hand_count = 1

    engine.execute_action(state, action_id(engine, state, card_name="juedou", target_id=target.id))
    action_ids = [action.action_id for action in engine.refresh_legal_actions(state)]
    assert action_ids == ["pass_response"]


def test_public_state_includes_distances_and_attack_ranges():
    engine, state = make_game()
    force_human_play(engine, state)
    human = state.players[0]
    target = state.players[2]
    human.equipment.weapon = Card(id="test-weapon", name="qinggangjian", suit="spade", rank="6")

    public = public_state_for_human(state)
    distance = next(
        item
        for item in public["distances"]
        if item["source_player_id"] == human.id and item["target_player_id"] == target.id
    )
    assert distance["distance"] >= 1
    assert distance["attack_range"] == 2
    assert distance["in_attack_range"] == (distance["distance"] <= 2)


def test_jiedaosharen_transfers_weapon_to_source_when_target_declines_sha():
    engine, state = make_game()
    source, target, victim = state.players[0], state.players[1], state.players[2]
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    for player in state.players:
        player.hand = []
        player.hand_count = 0
    source.hand = [Card(id="test-jiedao", name="jiedaosharen", suit="club", rank="Q")]
    source.hand_count = 1
    target.equipment.weapon = Card(id="test-weapon", name="qinggangjian", suit="spade", rank="6")

    engine.execute_action(state, action_id(engine, state, card_name="jiedaosharen", target_id=target.id, secondary_target_id=victim.id))
    assert target.equipment.weapon is None
    assert any(card.id == "test-weapon" for card in source.hand)


def test_shandian_deals_three_damage_on_hit():
    engine, state = make_game()
    player = state.players[0]
    state.current_player_index = 0
    state.pending_response = None
    player.hp = 3
    player.judgment_area = [Card(id="test-shandian", name="shandian", suit="heart", rank="Q")]
    state.deck = [Card(id="judge-spade-2", name="sha", suit="spade", rank="2")]
    state.discard_pile = []

    engine.start_turn(state)
    assert player.hp == 0
    assert state.pending_response is not None
    assert state.pending_response.type == "dying_tao"
    assert any("受到 3 点雷电伤害" in event for event in state.recent_events)


def test_illegal_action_is_rejected():
    engine, state = make_game()
    force_human_play(engine, state)
    with pytest.raises(ValueError):
        engine.execute_action(state, "not-a-real-action")


def test_public_state_hides_other_hands():
    _, state = make_game()
    public = public_state_for_human(state)
    for player in public["players"]:
        if player["is_human"]:
            assert len(player["hand"]) == player["hand_count"]
        else:
            assert player["hand"] == []
            expected = 6 if player["id"] == public["players"][public["current_player_index"]]["id"] else 4
            assert player["hand_count"] == expected


def test_public_state_does_not_leak_ai_api_key():
    _, state = make_game()
    public = public_state_for_human(state)
    assert "api_key" not in str(public)


def test_public_state_reveals_all_roles_after_game_over():
    _, state = make_game()
    state.winner = "fan"
    public = public_state_for_human(state)
    assert all(player["role"] != "unknown" for player in public["players"])


def test_recent_events_keeps_thirty_entries():
    engine, state = make_game()
    for index in range(35):
        engine._event(state, f"事件 {index}")  # noqa: SLF001 - 这里验证日志裁剪边界

    public = public_state_for_human(state)
    assert len(state.recent_events) == 30
    assert len(public["recent_events"]) == 30
    assert public["recent_events"][0] == "事件 5"


def test_ai_strategy_filters_zhong_sha_against_lord():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    lord = state.players[0]
    loyalist = state.players[1]
    assert lord.role == "zhu"
    assert loyalist.role == "zhong"

    state.current_player_index = 1
    state.phase = "play"
    state.pending_response = None
    loyalist.used_sha_this_turn = False
    loyalist.hand = [Card(id="test-sha", name="sha", suit="spade", rank="7")]

    legal = engine.refresh_legal_actions(state)
    assert any(action.card_name == "sha" and action.target_player_id == lord.id for action in legal)

    ai_legal = engine.ai_legal_actions(state, loyalist, legal)
    assert not any(action.card_name == "sha" and action.target_player_id == lord.id for action in ai_legal)
    assert any(action.card_name == "sha" and action.target_player_id != lord.id for action in ai_legal)


def test_ai_strategy_prefers_rebel_sha_against_lord():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    lord = state.players[0]
    rebel = state.players[2]
    assert lord.role == "zhu"
    assert rebel.role == "fan"

    state.current_player_index = 2
    state.phase = "play"
    state.pending_response = None
    rebel.used_sha_this_turn = False
    rebel.hand = [Card(id="test-sha", name="sha", suit="spade", rank="7")]
    rebel.equipment.weapon = Card(id="test-weapon", name="qinglongyanyuedao", suit="spade", rank="5")

    ai_legal = engine.ai_legal_actions(state, rebel, engine.refresh_legal_actions(state))
    assert any(action.card_name == "sha" and action.target_player_id == lord.id for action in ai_legal)
    assert ai_legal[0].card_name == "sha"
    assert ai_legal[0].target_player_id == lord.id


def test_ai_strategy_prefers_sha_before_other_attacks():
    engine, state = make_game()
    force_human_play(engine, state)
    actor = state.players[0]
    actor.is_human = False
    actor.hand = [
        Card(id="test-sha", name="sha", suit="spade", rank="7"),
        Card(id="test-juedou", name="juedou", suit="diamond", rank="A"),
    ]
    actor.hand_count = len(actor.hand)
    actor.used_sha_this_turn = False

    ai_legal = engine.ai_legal_actions(state, actor, engine.refresh_legal_actions(state))
    assert ai_legal
    assert ai_legal[0].card_name == "sha"
    assert any(action.card_name == "juedou" for action in ai_legal)
    assert any(action.action_id == "end_phase" for action in ai_legal)


def test_ai_strategy_does_not_hide_loyalist_from_lord():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    lord = state.players[0]
    loyalist = state.players[1]
    assert lord.role == "zhu"
    assert loyalist.role == "zhong"

    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    lord.used_sha_this_turn = False
    lord.is_human = False
    lord.hand = [Card(id="test-sha", name="sha", suit="spade", rank="7")]

    legal = engine.refresh_legal_actions(state)
    assert any(action.card_name == "sha" and action.target_player_id == loyalist.id for action in legal)
    ai_legal = engine.ai_legal_actions(state, lord, legal)
    assert ai_legal
    assert any(action.card_name == "sha" and action.target_player_id == loyalist.id for action in ai_legal)


def test_ai_strategy_does_not_hide_rebel_teammate_from_rebel_when_lord_unavailable():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    rebel = state.players[2]
    rebel_teammate = state.players[3]
    assert rebel.role == "fan"
    assert rebel_teammate.role == "fan"

    state.players[0].alive = False
    state.current_player_index = 2
    state.phase = "play"
    state.pending_response = None
    rebel.used_sha_this_turn = False
    rebel.hand = [Card(id="test-sha", name="sha", suit="spade", rank="7")]

    legal = engine.refresh_legal_actions(state)
    assert any(action.card_name == "sha" and action.target_player_id == rebel_teammate.id for action in legal)
    ai_legal = engine.ai_legal_actions(state, rebel, legal)
    assert ai_legal
    assert any(action.card_name == "sha" and action.target_player_id == rebel_teammate.id for action in ai_legal)


def test_ai_strategy_responds_with_shan_when_available():
    engine, state = make_game()
    ai = next(player for player in state.players if not player.is_human)
    source = next(player for player in state.players if player.id != ai.id)
    ai.hand = [Card(id="test-shan", name="shan", suit="heart", rank="2")]
    state.phase = "response"
    state.pending_response = PendingResponse(type="respond_shan", player_id=ai.id, source_player_id=source.id)

    ai_legal = engine.ai_legal_actions(state, ai, engine.refresh_legal_actions(state))
    assert [action.type for action in ai_legal] == ["respond_shan"]


def test_discard_actions_bind_specific_card_ids():
    engine, state = make_game()
    human = state.players[0]
    human.hand = [
        Card(id="sha-1", name="sha", suit="spade", rank="1"),
        Card(id="sha-2", name="sha", suit="spade", rank="2"),
        Card(id="sha-3", name="sha", suit="spade", rank="3"),
        Card(id="shan-1", name="shan", suit="heart", rank="4"),
        Card(id="shan-2", name="shan", suit="heart", rank="5"),
        Card(id="tao-1", name="tao", suit="diamond", rank="6"),
    ]
    state.phase = "discard"
    state.pending_response = PendingResponse(type="discard", player_id=human.id, required_count=2)

    actions = engine.refresh_legal_actions(state)
    combos = [tuple(action.target_card_ids or []) for action in actions]
    assert len(combos) == len(set(combos))
    assert ("sha-1", "sha-2") in combos
    assert ("tao-1", "tao-1") not in combos


def test_discard_by_card_ids_takes_exact_cards():
    engine, state = make_game()
    human = state.players[0]
    human.hand = [
        Card(id="sha-1", name="sha", suit="spade", rank="1"),
        Card(id="sha-2", name="sha", suit="spade", rank="2"),
        Card(id="sha-3", name="sha", suit="spade", rank="3"),
    ]
    state.current_player_index = 0
    state.phase = "discard"
    state.pending_response = PendingResponse(type="discard", player_id=human.id, required_count=2)

    engine.execute_action(state, "discard:sha-1,sha-3")
    assert [card.id for card in state.discard_pile] == ["sha-1", "sha-3"]
    assert [card.id for card in human.hand] == ["sha-2"]


def test_ai_prompt_includes_strict_role_policy():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    loyalist = state.players[1]
    state.current_player_index = 1
    state.phase = "play"
    state.pending_response = None
    legal = engine.ai_legal_actions(state, loyalist, engine.refresh_legal_actions(state))

    payload = compact_prompt(state, loyalist, legal)
    assert payload["role_policy"]["forbidden"]
    assert "主公" in "".join(payload["role_policy"]["forbidden"])
    assert "unknown" in " ".join(payload["decision_guidance"])
    assert "不要保守" in "".join(payload["aggressive_strategy"])
    assert "决斗不受距离限制" in payload["card_rules"]["trick"]["juedou"]
    assert "targeting_policy" in payload["card_rules"]
    assert "response_policy" in payload["card_rules"]
    assert "camp_win_strategy" in payload["card_rules"]
    assert "action_priority" in payload["card_rules"]
    assert "阵营赢" in "".join(payload["aggressive_strategy"])
    assert payload["valid_action_ids"] == [action.action_id for action in legal]
    assert any("valid_action_ids" in item for item in payload["decision_guidance"])


def test_ai_auto_selects_single_legal_action_without_llm():
    engine, state = make_game()
    actor = state.players[1]
    actor.is_human = False
    actor.hand = []
    actor.hand_count = 0
    state.current_player_index = 1
    state.phase = "play"
    state.pending_response = None

    class FailingLLM:
        async def choose_action(self, *_args, **_kwargs):
            raise AssertionError("LLM should not be called for a single legal action")

    engine.llm_client = FailingLLM()
    asyncio.run(engine.step_ai(state))
    assert any("结束回合" in event for event in state.recent_events)


def test_ai_still_calls_llm_when_multiple_legal_actions():
    engine, state = make_game()
    actor, target = state.players[1], state.players[0]
    actor.is_human = False
    actor.hand = [Card(id="test-sha", name="sha", suit="spade", rank="7")]
    actor.hand_count = 1
    actor.used_sha_this_turn = False
    target.hand = []
    target.hand_count = 0
    state.current_player_index = 1
    state.phase = "play"
    state.pending_response = None

    calls = []

    class RecordingLLM:
        async def choose_action(self, _config, _payload, legal_actions, _timeout_seconds):
            calls.append([action.action_id for action in legal_actions])
            return next(action.action_id for action in legal_actions if action.card_name == "sha")

    engine.llm_client = RecordingLLM()
    asyncio.run(engine.step_ai(state))
    assert calls


def test_lord_prompt_uses_inference_not_hidden_role_knowledge():
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name="AI-1"), AIConfig(name="AI-2"), AIConfig(name="AI-3")],
            seed=5,
        )
    )
    lord = state.players[0]
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    legal = engine.ai_legal_actions(state, lord, engine.refresh_legal_actions(state))

    payload = compact_prompt(state, lord, legal)
    hidden_roles = {player["id"]: player["role"] for player in payload["public_players"] if player["id"] != lord.id}
    assert hidden_roles["p1"] == "unknown"
    assert payload["role_policy"]["forbidden"] == []
    preferred = "".join(payload["role_policy"]["preferred"])
    assert "疑似反贼" in preferred
    assert "疑似忠臣" in preferred


def test_health_api():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
