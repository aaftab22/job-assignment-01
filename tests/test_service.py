import asyncio
from datetime import datetime, timezone

from telemetry_gateway.models import (
    BootRegistrationResult,
    DeviceState,
    IngestResult,
    TelemetryInput,
)
from telemetry_gateway.service import TelemetryService


def make_event() -> TelemetryInput:
    return TelemetryInput.model_validate(
        {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "sequence": 1,
            "deviceTime": "2026-08-12T09:00:00Z",
            "metric": "temperature",
            "value": 21.4,
        }
    )


def make_state(**overrides) -> DeviceState:
    fields = dict(
        device_id="device-01",
        boot_id="boot-a",
        generation=1,
        sequence=1,
        device_time="2026-08-12T09:00:00+00:00",
        received_at="2026-08-12T09:00:01+00:00",
        metric="temperature",
        value=21.4,
    )
    fields.update(overrides)
    return DeviceState(**fields)


class FakeRepository:
    def __init__(self, result: IngestResult) -> None:
        self._result = result
        self.ingest_calls = 0

    def register_boot(self, _event):
        return BootRegistrationResult("device-01", "boot-a", 1, True)

    def preview_state(self, _event, _received_at):
        # Sentinel distinct from the committed state so tests can detect if the
        # service incorrectly publishes from preview_state() instead of ingest().
        return make_state(value=999.0)

    def ingest(self, _event, _received_at):
        self.ingest_calls += 1
        return self._result

    def list_current_states(self):
        return []

    def list_events(self, _limit):
        return []

    def ping(self):
        return True


class FailingRepository(FakeRepository):
    def ingest(self, _event, _received_at):
        raise RuntimeError("db failure")


class RecordingPublisher:
    def __init__(self) -> None:
        self.states: list[DeviceState] = []

    async def publish(self, state: DeviceState) -> None:
        self.states.append(state)


def make_service(result: IngestResult, publisher: RecordingPublisher) -> TelemetryService:
    return TelemetryService(
        FakeRepository(result),
        publisher,
        now=lambda: datetime(2026, 8, 12, 9, 0, 1, tzinfo=timezone.utc),
    )


def test_committed_state_is_published_after_ingest() -> None:
    committed = make_state(value=21.4)
    publisher = RecordingPublisher()
    service = make_service(IngestResult(False, True, committed), publisher)

    result = asyncio.run(service.ingest(make_event()))

    assert result.current_changed is True
    # Must be the committed state, not the preview sentinel (value=999.0).
    assert publisher.states == [committed]


def test_no_publish_when_current_state_unchanged() -> None:
    publisher = RecordingPublisher()
    for result in [
        IngestResult(duplicate=True, current_changed=False),
        IngestResult(duplicate=False, current_changed=False),
    ]:
        service = make_service(result, publisher)
        asyncio.run(service.ingest(make_event()))

    assert publisher.states == []


def test_failed_ingest_does_not_publish() -> None:
    publisher = RecordingPublisher()
    service = TelemetryService(
        FailingRepository(IngestResult(False, True, make_state())),
        publisher,
        now=lambda: datetime(2026, 8, 12, 9, 0, 1, tzinfo=timezone.utc),
    )

    try:
        asyncio.run(service.ingest(make_event()))
        raise AssertionError("Expected RuntimeError was not raised")
    except RuntimeError:
        pass

    assert publisher.states == []
