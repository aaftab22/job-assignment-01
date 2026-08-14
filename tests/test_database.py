import sqlite3

from telemetry_gateway.database import TelemetryStore
from telemetry_gateway.migrations import apply_migrations, migration_001
from telemetry_gateway.models import BootRegistrationInput, TelemetryInput


def telemetry(**overrides) -> TelemetryInput:
    values = {
        "deviceId": "device-01",
        "bootId": "boot-a",
        "sequence": 1,
        "deviceTime": "2026-08-12T09:00:00+00:00",
        "metric": "temperature",
        "value": 21.4,
    }
    values.update(overrides)
    return TelemetryInput.model_validate(values)


def test_registers_a_boot_idempotently() -> None:
    store = TelemetryStore(":memory:")
    try:
        event = BootRegistrationInput(deviceId="device-01", bootId="boot-a")

        first = store.register_boot(event)
        second = store.register_boot(event)

        assert first.to_api() == {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "generation": 1,
            "created": True,
        }
        assert second.to_api() == {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "generation": 1,
            "created": False,
        }
    finally:
        store.close()


def test_stores_a_basic_event_and_calculates_current_state() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))

        result = store.ingest(telemetry(), "2026-08-12T09:00:01+00:00")

        assert result.duplicate is False
        assert result.current_changed is True
        assert store.list_current_states()[0].to_api() == {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "generation": 1,
            "sequence": 1,
            "deviceTime": "2026-08-12T09:00:00+00:00",
            "receivedAt": "2026-08-12T09:00:01+00:00",
            "metric": "temperature",
            "value": 21.4,
        }
        assert len(store.list_events(10)) == 1
    finally:
        store.close()


def test_repeated_event_from_same_boot_is_a_duplicate() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        store.ingest(telemetry(), "2026-08-12T09:00:01+00:00")

        duplicate = store.ingest(telemetry(), "2026-08-12T09:00:02+00:00")

        assert duplicate.to_api() == {
            "accepted": True,
            "duplicate": True,
            "currentChanged": False,
        }
        assert len(store.list_events(10)) == 1
    finally:
        store.close()


def test_same_sequence_from_different_boots_is_not_a_duplicate() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(
            BootRegistrationInput(deviceId="device-01", bootId="boot-a")
        )
        store.register_boot(
            BootRegistrationInput(deviceId="device-01", bootId="boot-b")
        )

        first = store.ingest(
            telemetry(bootId="boot-a", sequence=1),
            "2026-08-12T09:00:01+00:00",
        )
        second = store.ingest(
            telemetry(bootId="boot-b", sequence=1, value=22.4),
            "2026-08-12T09:00:02+00:00",
        )

        assert first.duplicate is False
        assert second.duplicate is False
        assert len(store.list_events(10)) == 2
    finally:
        store.close()


def test_migration_002_preserves_data_and_enforces_boot_scoped_uniqueness() -> None:
    # Build a version-1 database manually: apply migration_001, record it, seed one event.
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        migration_001(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (1, datetime('now'))"
        )

        # Seed the parent boot and one telemetry event under the old schema.
        conn.execute(
            "INSERT INTO device_boots (device_id, boot_id, generation, registered_at) "
            "VALUES ('device-01', 'boot-a', 1, '2026-08-12T09:00:00')"
        )
        conn.execute(
            "INSERT INTO telemetry_events "
            "    (device_id, boot_id, generation, sequence, device_time, received_at, metric, value) "
            "VALUES ('device-01', 'boot-a', 1, 1, '2026-08-12T09:00:00', '2026-08-12T09:00:01', 'temperature', 21.4)"
        )

        applied_before = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert 2 not in applied_before

        # Run the application's migration runner; it must skip version 1 and apply version 2.
        apply_migrations(conn)

        applied_after = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert 2 in applied_after

        row = conn.execute(
            "SELECT device_id, boot_id, generation, sequence, metric, value "
            "FROM telemetry_events"
        ).fetchone()
        assert row is not None
        assert row["device_id"] == "device-01"
        assert row["boot_id"] == "boot-a"
        assert row["generation"] == 1
        assert row["sequence"] == 1
        assert row["metric"] == "temperature"
        assert row["value"] == 21.4

        try:
            conn.execute(
                "INSERT INTO telemetry_events "
                "    (device_id, boot_id, generation, sequence, device_time, received_at, metric, value) "
                "VALUES ('device-01', 'boot-a', 1, 1, '2026-08-12T09:00:00', '2026-08-12T09:00:03', 'temperature', 99.0)"
            )
            raise AssertionError("Expected UNIQUE constraint violation was not raised")
        except sqlite3.IntegrityError:
            pass  # expected: same logical event must be rejected

        conn.execute(
            "INSERT INTO device_boots (device_id, boot_id, generation, registered_at) "
            "VALUES ('device-01', 'boot-b', 2, '2026-08-12T10:00:00')"
        )
        conn.execute(
            "INSERT INTO telemetry_events "
            "    (device_id, boot_id, generation, sequence, device_time, received_at, metric, value) "
            "VALUES ('device-01', 'boot-b', 2, 1, '2026-08-12T10:00:00', '2026-08-12T10:00:01', 'temperature', 22.0)"
        )
        count = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_current_state_uses_generation_then_sequence_not_device_time() -> None:
    # Scenario A: a newer generation must win even when its deviceTime is earlier.
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-b"))

        store.ingest(
            telemetry(bootId="boot-a", sequence=1, value=10.0,
                      deviceTime="2026-08-12T12:00:00+00:00"),
            "2026-08-12T09:00:01+00:00",
        )

        # boot-b is generation 2; its device clock is behind boot-a's.
        result_a = store.ingest(
            telemetry(bootId="boot-b", sequence=1, value=20.0,
                      deviceTime="2026-08-12T08:00:00+00:00"),
            "2026-08-12T09:00:02+00:00",
        )

        assert result_a.current_changed is True
        assert store.list_current_states()[0].to_api()["bootId"] == "boot-b"
        assert store.list_current_states()[0].to_api()["value"] == 20.0
    finally:
        store.close()

    # Scenario B: a higher sequence within the same generation must win even when its
    # deviceTime is earlier.
    store2 = TelemetryStore(":memory:")
    try:
        store2.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))

        store2.ingest(
            telemetry(bootId="boot-a", sequence=2, value=30.0,
                      deviceTime="2026-08-12T10:00:00+00:00"),
            "2026-08-12T09:00:01+00:00",
        )

        # sequence=3 arrives out of order with an earlier device clock.
        result_b = store2.ingest(
            telemetry(bootId="boot-a", sequence=3, value=40.0,
                      deviceTime="2026-08-12T09:00:00+00:00"),
            "2026-08-12T09:00:02+00:00",
        )

        assert result_b.current_changed is True
        assert store2.list_current_states()[0].to_api()["sequence"] == 3
        assert store2.list_current_states()[0].to_api()["value"] == 40.0
    finally:
        store2.close()