from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.game.engine import GameEngine
from app.game.state import public_state_for_human
from app.main import app
from app.models import AIConfig, CreateGameRequest


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


def test_health_api():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
