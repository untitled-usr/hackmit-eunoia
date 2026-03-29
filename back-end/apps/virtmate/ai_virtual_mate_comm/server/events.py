from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class EventBus:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[session_id].add(ws)

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(ws)
                if not self._connections[session_id]:
                    self._connections.pop(session_id, None)

    async def publish(self, session_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(session_id, set()))
        if not targets:
            return
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[session_id].discard(ws)

