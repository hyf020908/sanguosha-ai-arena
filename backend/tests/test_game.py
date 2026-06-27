from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.game.engine import GameEngine
from app.game.state import public_state_for_human
from app.llm.prompt import compact_prompt
from app.main import app
from app.models import AIConfig, Card, CreateGameRequest, PendingResponse


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
    human.hp = human.max_hp
    assert not any(action.card_name == "tao" for action in engine.legal_actions(state))
    human.hp = human.max_hp - 1
    has_tao = any(card.name == "tao" for card in human.hand)
    assert any(action.card_name == "tao" for action in engine.legal_actions(state)) == has_tao


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
    assert len(sha_actions) == len(alive_targets)
    assert len(tao_actions) == 1


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
    assert any(action.action_id == f"play_sha:{lord.id}" for action in legal)

    ai_legal = engine.ai_legal_actions(state, loyalist, legal)
    assert not any(action.action_id == f"play_sha:{lord.id}" for action in ai_legal)
    assert all(action.card_name == "sha" for action in ai_legal)
    assert not any(action.action_id == "end_phase" for action in ai_legal)


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

    ai_legal = engine.ai_legal_actions(state, rebel, engine.refresh_legal_actions(state))
    assert [action.action_id for action in ai_legal] == [f"play_sha:{lord.id}"]


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

    ai_legal = engine.ai_legal_actions(state, lord, engine.refresh_legal_actions(state))
    assert any(action.action_id == f"play_sha:{loyalist.id}" for action in ai_legal)


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

    ai_legal = engine.ai_legal_actions(state, rebel, engine.refresh_legal_actions(state))
    assert any(action.action_id == f"play_sha:{rebel_teammate.id}" for action in ai_legal)


def test_ai_strategy_responds_with_shan_when_available():
    engine, state = make_game()
    ai = next(player for player in state.players if not player.is_human)
    source = next(player for player in state.players if player.id != ai.id)
    ai.hand = [Card(id="test-shan", name="shan", suit="heart", rank="2")]
    state.phase = "response"
    state.pending_response = PendingResponse(type="respond_shan", player_id=ai.id, source_player_id=source.id)

    ai_legal = engine.ai_legal_actions(state, ai, engine.refresh_legal_actions(state))
    assert [action.action_id for action in ai_legal] == ["respond_shan"]


def test_discard_actions_are_grouped_by_card_names():
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
    combos = [tuple(action.target_card_names or []) for action in actions]
    assert len(combos) == len(set(combos))
    assert ("sha", "sha") in combos
    assert combos.count(("sha", "sha")) == 1
    assert ("tao", "tao") not in combos


def test_discard_by_card_names_randomly_takes_matching_cards():
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

    engine.execute_action(state, "discard:sha,sha")
    assert [card.name for card in state.discard_pile] == ["sha", "sha"]
    assert [card.name for card in human.hand] == ["sha"]


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
