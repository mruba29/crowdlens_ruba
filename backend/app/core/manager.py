import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {"crowd": [], "alerts": []}

    async def connect(self, channel: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(channel, []).append(ws)

    def disconnect(self, channel: str, ws: WebSocket):
        if ws in self.active.get(channel, []):
            self.active[channel].remove(ws)

    async def broadcast(self, channel: str, payload: dict):
        dead = []
        for ws in self.active.get(channel, []):
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(channel, d)


manager = ConnectionManager()
