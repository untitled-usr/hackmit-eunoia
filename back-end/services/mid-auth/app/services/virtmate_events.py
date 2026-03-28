"""In-memory event bus for VirtMate websocket sessions."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class VirtmateEventBus:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, key: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[key].add(ws)

    async def disconnect(self, key: str, ws: WebSocket) -> None:
        async with self._lock:
            if key in self._connections:
                self._connections[key].discard(ws)
                if not self._connections[key]:
                    self._connections.pop(key, None)

    async def publish(self, key: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(key, set()))
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
                    self._connections[key].discard(ws)


virtmate_event_bus = VirtmateEventBus()

