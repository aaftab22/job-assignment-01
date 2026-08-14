import asyncio

from telemetry_gateway.models import DeviceState
from telemetry_gateway.realtime import RealtimeHub


class FakeClient:
    def __init__(self, slow: bool = False, error: bool = False) -> None:
        self.slow = slow
        self.error = error
        self.messages: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, message: dict) -> None:
        if self.error:
            raise RuntimeError("simulated send error")
        if self.slow:
            await asyncio.sleep(0.5)
        self.messages.append(message)


def make_state() -> DeviceState:
    return DeviceState(
        device_id="device-01",
        boot_id="boot-a",
        generation=1,
        sequence=1,
        device_time="2026-08-12T09:00:00+00:00",
        received_at="2026-08-12T09:00:01+00:00",
        metric="temperature",
        value=21.4,
    )


class OrderedSet(list):
    def discard(self, item):
        if item in self:
            self.remove(item)


def test_slow_client_is_dropped_while_fast_client_receives() -> None:
    # Use a very short timeout so the test completes quickly.
    hub = RealtimeHub(send_timeout=0.05)
    fast_client = FakeClient()
    slow_client = FakeClient(slow=True)

    # Force the iteration order so slow_client is encountered first
    hub._clients = OrderedSet([slow_client, fast_client])

    async def run() -> None:
        await hub.publish(make_state())

    asyncio.run(run())

    assert len(fast_client.messages) == 1
    assert len(slow_client.messages) == 0
    assert hub.size == 1
    assert fast_client in hub._clients
    assert slow_client not in hub._clients


def test_error_client_is_dropped_while_good_client_receives() -> None:
    hub = RealtimeHub(send_timeout=0.05)
    good_client = FakeClient()
    error_client = FakeClient(error=True)

    async def run() -> None:
        await hub.connect(good_client)
        await hub.connect(error_client)
        await hub.publish(make_state())

    asyncio.run(run())

    assert len(good_client.messages) == 1
    assert len(error_client.messages) == 0
    assert hub.size == 1
    assert good_client in hub._clients
    assert error_client not in hub._clients
