from __future__ import annotations

import pytest

from app.game.engine import GameEngine
from app.models import AIConfig, Card, CreateGameRequest, PendingResponse


def card(card_id: str, name: str, suit: str = "spade", rank: str = "7") -> Card:
    return Card(id=card_id, name=name, suit=suit, rank=rank)


def prepared_state(player_count: int = 4):
    engine = GameEngine()
    state = engine.create_game(
        CreateGameRequest(
            human_name="Human",
            ai_players=[AIConfig(name=f"AI-{index}") for index in range(1, player_count)],
            seed=11,
        )
    )
    state.current_player_index = 0
    state.phase = "play"
    state.pending_response = None
    state.winner = None
    for index, player in enumerate(state.players):
        player.alive = True
        player.hp = 4
        player.max_hp = 4
        player.hand = []
        player.hand_count = 0
        player.judgment_area = []
        player.equipment.weapon = None
        player.equipment.armor = None
        player.equipment.attack_horse = None
        player.equipment.defense_horse = None
        player.role_public = index == 0
    return engine, state


def find_action(engine: GameEngine, state, **kwargs) -> str:
    for action in engine.refresh_legal_actions(state):
        if all(getattr(action, key) == value for key, value in kwargs.items()):
            return action.action_id
    raise AssertionError(f"未找到动作：{kwargs}")


def all_card_ids(state) -> list[str]:
    ids = [item.id for item in state.deck + state.discard_pile]
    for player in state.players:
        ids.extend(item.id for item in player.hand)
        ids.extend(item.id for item in player.judgment_area)
        for item in (
            player.equipment.weapon,
            player.equipment.armor,
            player.equipment.attack_horse,
            player.equipment.defense_horse,
        ):
            if item:
                ids.append(item.id)
    return ids


def test_guohe_cannot_target_self_or_empty_target():
    engine, state = prepared_state()
    source, empty_target, equipped_target = state.players[0], state.players[1], state.players[2]
    source.hand = [card("guohe", "guohechaiqiao"), card("self-card", "sha")]
    source.hand_count = len(source.hand)
    equipped_target.equipment.weapon = card("weapon", "qinggangjian")

    actions = engine.refresh_legal_actions(state)
    guohe_targets = [action.target_player_id for action in actions if action.card_name == "guohechaiqiao"]
    assert source.id not in guohe_targets
    assert empty_target.id not in guohe_targets
    assert equipped_target.id in guohe_targets

    with pytest.raises(ValueError):
        engine.execute_action(state, f"play_guohechaiqiao:guohe:{source.id}:hand:random")


def test_jiedaosharen_requires_choice_and_pass_transfers_weapon():
    engine, state = prepared_state()
    source, target, victim = state.players[0], state.players[1], state.players[2]
    source.hand = [card("jiedao", "jiedaosharen", "club", "Q")]
    source.hand_count = 1
    target.hand = [card("sha", "sha")]
    target.hand_count = 1
    target.equipment.weapon = card("weapon", "qinggangjian", "spade", "6")

    engine.execute_action(state, find_action(engine, state, card_name="jiedaosharen", target_player_id=target.id, secondary_target_player_id=victim.id))
    assert state.pending_response is not None
    assert state.pending_response.type == "respond_sha"
    assert state.pending_response.player_id == target.id
    assert {action.type for action in engine.refresh_legal_actions(state)} == {"respond_sha", "pass_response"}

    engine.execute_action(state, "pass_response")
    assert target.equipment.weapon is None
    assert any(item.id == "weapon" for item in source.hand)


def test_jiedaosharen_nested_sha_returns_to_trick_user_after_shan():
    engine, state = prepared_state()
    source, target, victim = state.players[0], state.players[1], state.players[2]
    source.hand = [card("jiedao", "jiedaosharen", "club", "Q")]
    source.hand_count = 1
    target.hand = [card("sha", "sha")]
    target.hand_count = 1
    target.equipment.weapon = card("weapon", "qinggangjian", "spade", "6")
    victim.hand = [card("shan", "shan", "heart", "2")]
    victim.hand_count = 1

    engine.execute_action(state, find_action(engine, state, card_name="jiedaosharen", target_player_id=target.id, secondary_target_player_id=victim.id))
    engine.execute_action(state, find_action(engine, state, type="respond_sha"))
    assert state.pending_response is not None
    assert state.pending_response.type == "respond_shan"
    engine.execute_action(state, find_action(engine, state, type="respond_shan"))
    assert state.current_player_index == 0
    assert state.phase == "play"


def test_shandian_moves_without_duplication_and_skips_existing_shandian():
    engine, state = prepared_state()
    current, skipped, receiver = state.players[0], state.players[1], state.players[2]
    state.current_player_index = 0
    current.judgment_area = [card("lightning", "shandian", "heart", "Q")]
    skipped.judgment_area = [card("other-lightning", "shandian", "spade", "A")]
    state.deck = [card("judge", "sha", "heart", "K"), card("draw1", "sha"), card("draw2", "sha")]
    state.discard_pile = []

    engine.start_turn(state)
    assert not any(item.id == "lightning" for item in current.judgment_area)
    assert any(item.id == "lightning" for item in receiver.judgment_area)
    assert not any(item.id == "lightning" for item in state.discard_pile)
    ids = all_card_ids(state)
    assert len(ids) == len(set(ids))


def test_shandian_hit_survivor_still_draws_and_enters_play():
    engine, state = prepared_state()
    player = state.players[0]
    state.current_player_index = 0
    player.hp = 4
    player.judgment_area = [card("lightning", "shandian", "heart", "Q")]
    state.deck = [card("judge", "sha", "spade", "2"), card("draw1", "sha"), card("draw2", "shan")]

    engine.start_turn(state)
    assert player.hp == 1
    assert state.phase == "play"
    assert [item.id for item in player.hand] == ["draw1", "draw2"]


def test_delayed_tricks_judge_last_in_first_out():
    engine, state = prepared_state()
    player = state.players[0]
    state.current_player_index = 0
    player.judgment_area = [card("lebu", "lebusishu", "club", "6"), card("lightning", "shandian", "heart", "Q")]
    state.deck = [card("judge-lightning", "sha", "heart", "K"), card("judge-lebu", "sha", "heart", "A")]

    engine.start_turn(state)
    lightning_event = next(index for index, event in enumerate(state.recent_events) if "闪电" in event and "未命中" in event)
    lebu_event = next(index for index, event in enumerate(state.recent_events) if "乐不思蜀判定" in event)
    assert lightning_event < lebu_event


def test_delayed_trick_enters_judgment_only_after_wuxie_window():
    engine, state = prepared_state()
    source, target, responder = state.players[0], state.players[1], state.players[2]
    source.hand = [card("lebu", "lebusishu", "club", "6")]
    source.hand_count = 1
    responder.hand = [card("wuxie", "wuxiekeji", "club", "Q")]
    responder.hand_count = 1

    engine.execute_action(state, find_action(engine, state, card_name="lebusishu", target_player_id=target.id))
    assert state.pending_response is not None
    assert state.pending_response.type == "wuxie"
    engine.execute_action(state, find_action(engine, state, type="wuxie"))
    assert not target.judgment_area
    assert any(item.id == "lebu" for item in state.discard_pile)


def test_qinggang_only_disables_bagua_for_sha_not_wanjian():
    engine, state = prepared_state()
    source, target = state.players[0], state.players[1]
    source.hand = [card("sha", "sha", "spade", "7")]
    source.hand_count = 1
    source.equipment.weapon = card("qinggang", "qinggangjian")
    target.equipment.armor = card("bagua", "baguazhen")
    state.deck = [card("judge-red", "sha", "heart", "K")]

    engine.execute_action(state, find_action(engine, state, card_name="sha", target_player_id=target.id))
    assert not any("八卦阵判定成功" in event for event in state.recent_events)

    engine, state = prepared_state()
    source, target = state.players[0], state.players[1]
    source.hand = [card("wanjian", "wanjianqifa", "heart", "A")]
    source.hand_count = 1
    source.equipment.weapon = card("qinggang", "qinggangjian")
    target.equipment.armor = card("bagua", "baguazhen")
    state.deck = [card("judge-red", "sha", "heart", "K")]

    engine.execute_action(state, find_action(engine, state, card_name="wanjianqifa"))
    assert any("八卦阵判定成功" in event for event in state.recent_events)


def test_card_id_actions_remove_exact_play_and_response_cards():
    engine, state = prepared_state()
    source, target = state.players[0], state.players[1]
    source.hand = [card("sha-1", "sha", "spade", "7"), card("sha-2", "sha", "heart", "8")]
    source.hand_count = 2

    engine.execute_action(state, next(action.action_id for action in engine.refresh_legal_actions(state) if action.card_id == "sha-2" and action.target_player_id == target.id))
    assert any(item.id == "sha-2" for item in state.discard_pile)
    assert [item.id for item in source.hand] == ["sha-1"]

    state.pending_response = PendingResponse(type="respond_shan", player_id=target.id, source_player_id=source.id)
    target.hand = [card("shan-1", "shan", "heart", "2"), card("shan-2", "shan", "diamond", "3")]
    target.hand_count = 2
    engine.execute_action(state, next(action.action_id for action in engine.refresh_legal_actions(state) if action.card_id == "shan-2"))
    assert any(item.id == "shan-2" for item in state.discard_pile)
    assert [item.id for item in target.hand] == ["shan-1"]


def test_chai_and_shun_can_select_public_area_cards_without_leaking_hand():
    engine, state = prepared_state()
    source, target = state.players[0], state.players[1]
    source.hand = [card("guohe", "guohechaiqiao"), card("shun", "shunshouqianyang", "spade", "3")]
    source.hand_count = 2
    target.hand = [card("hidden", "tao", "heart", "3")]
    target.hand_count = 1
    target.equipment.weapon = card("weapon", "qinggangjian")
    target.judgment_area = [card("lebu", "lebusishu", "club", "6")]

    actions = engine.refresh_legal_actions(state)
    assert any(action.card_name == "guohechaiqiao" and action.selected_area == "hand" and action.selected_card_id is None for action in actions)
    assert any(action.card_name == "guohechaiqiao" and action.selected_card_id == "weapon" for action in actions)
    assert any(action.card_name == "guohechaiqiao" and action.selected_card_id == "lebu" for action in actions)

    engine.execute_action(state, find_action(engine, state, card_name="guohechaiqiao", selected_card_id="weapon"))
    assert target.equipment.weapon is None
    assert any(item.id == "weapon" for item in state.discard_pile)


def test_wugufengdeng_uses_public_pool_and_sequential_choice():
    engine, state = prepared_state(3)
    source = state.players[0]
    source.hand = [card("wugu", "wugufengdeng", "heart", "3")]
    source.hand_count = 1
    state.deck = [card("pool-1", "tao", "heart", "3"), card("pool-2", "sha"), card("pool-3", "shan", "diamond", "2")]

    engine.execute_action(state, find_action(engine, state, card_name="wugufengdeng"))
    assert state.pending_response is not None
    assert state.pending_response.type == "wugu"
    assert len(state.pending_response.wugu_pool or []) == 3
    engine.execute_action(state, "wugu_choose:pool-1")
    assert any(item.id == "pool-1" for item in source.hand)
    assert len(state.pending_response.wugu_pool or []) == 2


def test_wuxie_chain_can_counter_wuxie_and_restore_original_effect():
    engine, state = prepared_state(3)
    source, first, second = state.players[0], state.players[1], state.players[2]
    source.hand = [card("wuzhong", "wuzhongshengyou", "heart", "7")]
    source.hand_count = 1
    first.hand = [card("wuxie-1", "wuxiekeji", "club", "Q")]
    first.hand_count = 1
    second.hand = [card("wuxie-2", "wuxiekeji", "diamond", "Q")]
    second.hand_count = 1
    state.deck = [card("draw-1", "sha"), card("draw-2", "shan", "heart", "2")]

    engine.execute_action(state, find_action(engine, state, card_name="wuzhongshengyou"))
    engine.execute_action(state, find_action(engine, state, type="wuxie"))
    assert state.pending_response is not None
    assert state.pending_response.wuxie_effect_cancelled is True
    engine.execute_action(state, find_action(engine, state, type="wuxie"))
    assert state.pending_response is None
    assert [item.id for item in source.hand] == ["draw-1", "draw-2"]


def test_tao_only_heals_self_in_play_phase():
    engine, state = prepared_state()
    source, target = state.players[0], state.players[1]
    source.hand = [card("tao", "tao", "heart", "3")]
    source.hand_count = 1
    source.hp = 3
    target.hp = 2

    legal = engine.refresh_legal_actions(state)
    assert any(action.card_name == "tao" and action.target_player_id == source.id for action in legal)
    assert not any(action.card_name == "tao" and action.target_player_id == target.id for action in legal)

    engine.execute_action(state, find_action(engine, state, card_name="tao", target_player_id=source.id))
    assert source.hp == 4
    assert target.hp == 2
    assert any(item.id == "tao" for item in state.discard_pile)


def test_duel_source_death_advances_to_alive_player():
    engine, state = prepared_state()
    source, target = state.players[2], state.players[3]
    source.role = "fan"
    target.role = "fan"
    state.current_player_index = 2
    source.hp = 1
    source.hand = [card("duel", "juedou", "diamond", "A")]
    source.hand_count = 1
    target.hand = [card("target-sha", "sha")]
    target.hand_count = 1

    engine.execute_action(state, find_action(engine, state, card_name="juedou", target_player_id=target.id))
    engine.execute_action(state, "respond_sha:target-sha")
    engine.execute_action(state, "pass_response")
    while state.pending_response and state.pending_response.type == "dying_tao":
        engine.execute_action(state, "pass_response")

    assert source.alive is False
    assert state.winner is None
    assert state.pending_response is None
    assert state.phase == "play"
    assert state.players[state.current_player_index].alive is True
    assert state.current_player_index != 2
    assert engine.refresh_legal_actions(state)


def test_shandian_death_advances_to_alive_player():
    engine, state = prepared_state()
    target = state.players[2]
    target.role = "fan"
    state.players[3].role = "fan"
    state.current_player_index = 2
    target.hp = 3
    target.judgment_area = [card("lightning", "shandian", "heart", "Q")]
    state.deck = [card("judge-spade-2", "sha", "spade", "2")]

    engine.start_turn(state)
    while state.pending_response and state.pending_response.type == "dying_tao":
        engine.execute_action(state, "pass_response")

    assert target.alive is False
    assert state.winner is None
    assert state.pending_response is None
    assert state.players[state.current_player_index].alive is True
    assert state.current_player_index != 2
    assert state.phase in {"play", "discard"}
    assert engine.refresh_legal_actions(state)


def test_identity_winners_and_death_rewards():
    engine, state = prepared_state(5)
    lord, loyalist, rebel, other_rebel, spy = state.players
    lord.role, loyalist.role, rebel.role, other_rebel.role, spy.role = "zhu", "zhong", "fan", "fan", "nei"
    lord.alive = False
    loyalist.alive = False
    rebel.alive = False
    other_rebel.alive = False
    spy.alive = True
    engine._check_winner(state)  # noqa: SLF001
    assert state.winner == "nei"

    engine, state = prepared_state(5)
    lord, loyalist, rebel, other_rebel, spy = state.players
    lord.role, loyalist.role, rebel.role, other_rebel.role, spy.role = "zhu", "zhong", "fan", "fan", "nei"
    lord.alive = False
    rebel.alive = True
    engine._check_winner(state)  # noqa: SLF001
    assert state.winner == "fan"

    engine, state = prepared_state(5)
    lord, loyalist, rebel, other_rebel, spy = state.players
    lord.role, loyalist.role, rebel.role, other_rebel.role, spy.role = "zhu", "zhong", "fan", "fan", "nei"
    rebel.alive = False
    other_rebel.alive = False
    spy.alive = False
    engine._check_winner(state)  # noqa: SLF001
    assert state.winner == "zhu"

    killer = lord
    state.deck = [card("reward-1", "sha"), card("reward-2", "sha"), card("reward-3", "sha")]
    rebel.alive = True
    rebel.role = "fan"
    before = len(killer.hand)
    engine._apply_death_rewards(state, rebel, killer)  # noqa: SLF001
    assert len(killer.hand) == before + 3

    loyalist.alive = True
    loyalist.role = "zhong"
    killer.hand = [card("lord-hand", "sha")]
    killer.equipment.weapon = card("lord-weapon", "qinggangjian")
    engine._apply_death_rewards(state, loyalist, killer)  # noqa: SLF001
    assert not killer.hand
    assert killer.equipment.weapon is None

    state.deck = [card("no-reward-1", "sha"), card("no-reward-2", "sha"), card("no-reward-3", "sha")]
    before_deck = len(state.deck)
    engine._apply_death_rewards(state, rebel, None)  # noqa: SLF001
    assert len(state.deck) == before_deck
