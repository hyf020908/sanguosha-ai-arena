from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.game.engine import GameEngine
from app.game.state import public_state_for_human
from app.models import CreateGameRequest, SubmitActionRequest
from app.storage.memory import games

router = APIRouter(prefix="/api/games", tags=["games"])
engine = GameEngine()


@router.post("")
async def create_game(request: CreateGameRequest) -> dict:
    try:
        state = engine.create_game(request)
        games[state.game_id] = state
        await engine.auto_advance_until_human(state)
        return {"game_id": state.game_id, "state": public_state_for_human(state)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{game_id}")
async def get_game(game_id: str) -> dict:
    state = _get_state(game_id)
    engine.refresh_legal_actions(state)
    return public_state_for_human(state)


@router.get("/{game_id}/legal-actions")
async def get_legal_actions(game_id: str) -> dict:
    state = _get_state(game_id)
    engine.refresh_legal_actions(state)
    actor = state.players[state.current_player_index]
    if state.pending_response:
        actor = next(player for player in state.players if player.id == state.pending_response.player_id)
    if not actor.is_human:
        return {"legal_actions": [], "message": "当前等待 AI 或系统自动推进"}
    return {"legal_actions": [action.model_dump() for action in state.legal_actions], "message": "ok"}


@router.post("/{game_id}/actions")
async def submit_action(game_id: str, request: SubmitActionRequest) -> dict:
    state = _get_state(game_id)
    try:
        actor = _human_actor_or_none(state)
        if actor is None:
            raise ValueError("当前不是人类操作时机")
        engine.execute_action(state, request.action_id)
        await engine.auto_advance_until_human(state)
        return public_state_for_human(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _get_state(game_id: str):
    state = games.get(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail="游戏不存在")
    return state


def _human_actor_or_none(state):
    if state.winner:
        return None
    if state.pending_response:
        actor = next(player for player in state.players if player.id == state.pending_response.player_id)
    else:
        actor = state.players[state.current_player_index]
    return actor if actor.is_human else None
