# Engineering decisions

## Invariants identified

- A repeated telemetry event must be idempotent and identified by `(deviceId, bootId, sequence)`.
- A new registered device boot must receive a newer server-side generation and remain distinct from previous boots.
- Current state must be ordered by boot generation and sequence, not by `deviceTime`.
- Raw telemetry history must be preserved, including events that do not become current state.
- Realtime state-change messages must only be published after a successful database transaction and when current state actually changes.
- A slow WebSocket client must not block healthy clients or cause unbounded memory use.
- The dashboard must fetch authoritative current state after a successful WebSocket reconnection.

## Incidents fixed

- Events from different device boots could be treated as duplicates because event uniqueness was scoped only to `(deviceId, sequence)`. After a reboot, the sequence could reset and collide with an older boot. Fixed by changing the uniqueness constraint to `(deviceId, bootId, sequence)`.

- Current state could be updated based on `deviceTime`, allowing an incorrect device clock to affect ordering. Fixed by using boot generation first and sequence second when determining which event becomes current state.

- Realtime state was published before the database transaction completed. This could publish speculative state, duplicate or stale events, or an update even when the database operation failed. Fixed by ingesting first and publishing only when `current_changed` is true.

- A slow WebSocket client could block delivery to other clients because `send_json()` was awaited serially without a timeout. Fixed by adding a configurable send timeout and dropping clients that do not respond within it.

- The dashboard did not reload the authoritative current-state snapshot after a WebSocket reconnection. Events received while it was disconnected could therefore be missed. Fixed by loading the snapshot again after successful reconnections.

## Design choices and trade-offs

- Rename-and-copy migration (Fix #1): SQLite does not support ALTER TABLE ... DROP CONSTRAINT. Used the standard pattern: create new table, copy data, drop old, rename. This preserves the received_at index and all existing rows.

- preview_state not removed (Fix #3): The method remains on the repository interface. It is no longer called in the ingest path, but removing it would be scope-expanding refactoring with no correctness benefit.

- Timeout-based slow-client detection (Fix #4): Used a wall-clock send_timeout (default 1.0s) rather than a byte-count buffer limit. This is simpler and sufficient for the contract. Trade-off: a transient 1 second network hiccup will disconnect a client, but the dashboard auto-reconnects in 1 second and re-fetches the snapshot (Fix #5).

- Drop vs. buffer-then-drop (Fix #4): Clients are dropped immediately on timeout, not buffered-then-dropped. A per-client message queue would be more resilient to brief stalls but adds significant complexity beyond the assignment scope.

- Static analysis test for frontend (Fix #5): No frontend test framework exists. Adding Jest or Playwright would introduce unnecessary dependencies. A structural regex test against app.js verifies the reconnect guard pattern and serves as a regression guard.

## Schema or API compatibility concerns

- Migration 002 preserves all existing telemetry data while changing the uniqueness constraint to include `boot_id`.

- No API response shapes or existing endpoint behavior were changed.

- `RealtimeHub.__init__` now accepts an optional `send_timeout` parameter with a default value, so existing callers remain compatible.

## Remaining risks or incomplete work

- **Transient WebSocket timeout (Fix #4):** A client with a temporary network delay longer than the 1-second timeout may be disconnected even if it is otherwise healthy. This is mitigated by the existing automatic reconnect and snapshot refresh after reconnect. A future improvement could allow clients to tolerate temporary delays instead of disconnecting immediately.

- **Reconnect snapshot race (Fix #5):** A realtime message could arrive while `loadSnapshot()` is fetching the snapshot after reconnect. If the snapshot is slightly older, it could overwrite that newer message. Fixing this would require generation/sequence-aware merging on the frontend, which is outside the scope of this assignment.