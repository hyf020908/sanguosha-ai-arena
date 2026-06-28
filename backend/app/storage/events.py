from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from contextlib import suppress
from typing import Any

from app.game.state import public_state_for_human
from app.models import GameState


class GameEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    def subscribe(self, game_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers[game_id].add(queue)
        return queue

    def unsubscribe(self, game_id: str, queue: asyncio.Queue[str]) -> None:
        subscribers = self._subscribers.get(game_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(game_id, None)

    def publish_state(self, state: GameState) -> None:
        subscribers = list(self._subscribers.get(state.game_id, set()))
        if not subscribers:
            return
        payload = self.state_event(state)
        for queue in subscribers:
            self._put_latest(queue, payload)

    def state_event(self, state: GameState) -> str:
        return self._sse("state", public_state_for_human(state))

    def _put_latest(self, queue: asyncio.Queue[str], payload: str) -> None:
        with suppress(asyncio.QueueFull):
            queue.put_nowait(payload)
            return
        with suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        with suppress(asyncio.QueueFull):
            queue.put_nowait(payload)

    def _sse(self, event: str, data: Any) -> str:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event}\ndata: {body}\n\n"


game_events = GameEventBroker()
