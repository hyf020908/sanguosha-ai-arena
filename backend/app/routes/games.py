from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.game.engine import GameEngine
from app.game.state import public_state_for_human
from app.models import CreateGameRequest, SubmitActionRequest
from app.storage.events import game_events
from app.storage.memory import games

router = APIRouter(prefix="/api/games", tags=["games"])
engine = GameEngine()


@router.post("")
async def create_game(request: CreateGameRequest) -> dict:
    try:
        state = engine.create_game(request)
        games[state.game_id] = state
        await engine.auto_advance_until_human(state)
        engine.refresh_legal_actions(state)
        game_events.publish_state(state)
        return {"game_id": state.game_id, "state": public_state_for_human(state)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{game_id}")
async def get_game(game_id: str) -> dict:
    state = _get_state(game_id)
    engine.refresh_legal_actions(state)
    return public_state_for_human(state)


@router.get("/{game_id}/stream")
async def stream_game(game_id: str, request: Request) -> StreamingResponse:
    state = _get_state(game_id)
    engine.refresh_legal_actions(state)
    queue = game_events.subscribe(game_id)

    async def events():
        try:
            yield game_events.state_event(state)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            game_events.unsubscribe(game_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        engine.refresh_legal_actions(state)
        game_events.publish_state(state)
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
