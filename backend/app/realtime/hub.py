"""Unified real-time hub.

One WebSocket channel `/ws/live` carries every real-time event the UI needs:
  - crowd_update       (per-frame metrics + SRI + prediction)
  - processing_stage   (analysis lifecycle)
  - alert              (new / updated alert)
  - incident           (new / updated incident)
  - system_health      (periodic health push)

Any backend code publishes via `hub.publish(type, payload)`; the hub fans out
to all connected clients. An in-process async pub/sub also lets services react
to each other without tight coupling.
"""
from __future__ import annotations
import asyncio
import contextlib
import datetime
import json
from typing import Any

from fastapi import WebSocket


class RealtimeHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        await ws.send_text(json.dumps({"type": "connected", "ts": _now()}))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if "ts" not in message:
            message["ts"] = _now()
        data = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def publish(self, msg_type: str, payload: dict[str, Any]) -> None:
        """Thread-safe fire-and-forget publish from sync code / worker threads."""
        message = {"type": msg_type, **payload}
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        else:  # pragma: no cover - fallback for tests
            with contextlib.suppress(RuntimeError):
                asyncio.get_event_loop().create_task(self.broadcast(message))


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


hub = RealtimeHub()
