"""Ingest-side heartbeat publisher (feat/panel-leds).

ingest publishes STATE_PATH (below — do not restate the path in prose; it has already
drifted once) on a 1 Hz tick driven from inside the RX loop, with an atomic temp+rename.
The publish is wrapped so no write failure escapes into
the radio loop: on failure the file goes stale and the supervisor lights RED (correct
degradation — indicator says don't-trust-me while ingest keeps capturing). `ts` (periodic
liveness) and `last_rx_ts` (traffic) are DISTINCT fields, so a quiet pad stays "alive".

Persistent-failure hardening (the bugs that only show after hours on a pad):
- the atomic write unlinks its temp on ANY failure — no slow fill of the small /run tmpfs;
- HeartbeatPublisher rate-limits the failure log to transitions (into failure / recovery),
  so a disk-full doesn't emit ~86k journal lines/day onto the same disk journald writes to.

Host-tested; no hardware.
"""
import json
import os

# Shared path for publisher (ingest) and reader (supervisor). /run is tmpfs (no SD wear on a
# 1 Hz rewrite, ephemeral per boot); /run/apogee is created rocketman-owned via
# RuntimeDirectory=apogee on apogee-ingest.service (and removed on stop -> file vanishes ->
# supervisor sees "down" -> RED, the correct degradation).
STATE_PATH = "/run/apogee/ingest-state.json"


def state_snapshot(ts, last_rx_ts=None, flight_open=False, write_ok=True, **extra) -> dict:
    """Build the published snapshot. `ts` (liveness) and `last_rx_ts` (traffic) stay
    separate so a quiet pad reads as alive, not stale. `extra` carries future fields
    (accepted counts, crc/foreign, per-SRC flight, ...) without a signature churn."""
    snap = {"ts": ts, "last_rx_ts": last_rx_ts, "flight_open": flight_open, "write_ok": write_ok}
    snap.update(extra)
    return snap


def write_state_atomic(path: str, snapshot: dict) -> None:
    """Atomic temp+rename. On ANY failure (write OR rename) unlink the temp and re-raise —
    never leak a .tmp that would slowly fill /run tmpfs at 1 Hz."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(snapshot, f)
        os.replace(tmp, path)                 # atomic on same filesystem
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def safe_publish(path: str, snapshot: dict) -> bool:
    """Publish; NEVER raise `Exception` into the caller — a failure just returns False (the
    file goes stale and the supervisor lights RED). Uses `except Exception`, NOT
    BaseException, so KeyboardInterrupt / SystemExit still propagate."""
    try:
        write_state_atomic(path, snapshot)
        return True
    except Exception:                          # noqa: BLE001 — must not reach the radio loop
        return False


class HeartbeatPublisher:
    """Stateful wrapper that rate-limits the failure log to transitions only: one line on
    entering failure, one on recovery, the rest suppressed — a disk-full at 1 Hz must not
    spew ~86k lines/day onto the same disk journald writes to (that makes it worse)."""

    def __init__(self, path: str, log=None):
        self._path = path
        self._log = log
        self._ok = True                        # healthy until proven otherwise

    def publish(self, snapshot: dict) -> bool:
        ok = safe_publish(self._path, snapshot)
        if not ok and self._ok:
            self._emit(f"heartbeat publish FAILING ({self._path}); suppressing further")
        elif ok and not self._ok:
            self._emit(f"heartbeat publish recovered ({self._path})")
        self._ok = ok
        return ok

    def _emit(self, msg: str) -> None:
        if self._log:
            self._log(msg)
