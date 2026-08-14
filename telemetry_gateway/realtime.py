from __future__ import annotations

import asyncio
from typing import Protocol

from fastapi import WebSocket

from telemetry_gateway.models import DeviceState


class StatePublisher(Protocol):
    async def publish(self, state: DeviceState) -> None: ...


class RealtimeHub:
    def __init__(self, send_timeout: float = 1.0) -> None:
        self._clients: set[WebSocket] = set()
        self._send_timeout = send_timeout

    async def connect(self, client: WebSocket) -> None:
        await client.accept()
        self._clients.add(client)

    def disconnect(self, client: WebSocket) -> None:
        self._clients.discard(client)

    async def publish(self, state: DeviceState) -> None:
        message = {"type": "device.state.changed", "data": state.to_api()}
        for client in tuple(self._clients):
            try:
                await asyncio.wait_for(
                    client.send_json(message), timeout=self._send_timeout
                )
            except Exception:
                self._clients.discard(client)

    @property
    def size(self) -> int:
        return len(self._clients)
