"""Tests for the ingest-side heartbeat publisher (ground.panel.heartbeat).

Load-bearing property: a heartbeat write failure must NEVER escape into the radio loop — it
returns False (file goes stale, supervisor lights RED), it does not raise. Plus the
persistent-failure hardening: no temp-file leak on rename failure, and a failure log
rate-limited to transitions. KeyboardInterrupt/SystemExit still propagate.
"""
import json
import os

import pytest

from ground.panel import heartbeat as hb
from ground.panel.heartbeat import (
    state_snapshot, write_state_atomic, safe_publish, HeartbeatPublisher,
)


def test_state_snapshot_keeps_liveness_and_rx_separate():
    snap = state_snapshot(
        ts="2026-07-30T18:00:00Z", last_rx_ts="2026-07-30T17:59:00Z",
        flight_open=True, write_ok=True,
    )
    assert snap["ts"] == "2026-07-30T18:00:00Z"
    assert snap["last_rx_ts"] == "2026-07-30T17:59:00Z"   # distinct: quiet pad stays alive
    assert snap["flight_open"] is True
    assert snap["write_ok"] is True


def test_write_atomic_writes_parseable_json(tmp_path):
    p = tmp_path / "state.json"
    write_state_atomic(str(p), {"ts": "x", "n": 1})
    assert json.loads(p.read_text()) == {"ts": "x", "n": 1}


def test_write_atomic_leaves_no_temp_on_success(tmp_path):
    p = tmp_path / "state.json"
    write_state_atomic(str(p), {"ts": "x"})
    assert [f for f in os.listdir(tmp_path) if f != "state.json"] == []


def test_write_atomic_unlinks_temp_on_rename_failure(tmp_path, monkeypatch):
    # rename fails after the temp is written -> the temp must NOT persist (else /run fills
    # at 1 Hz over hours). write re-raises, but leaves no .tmp behind.
    p = tmp_path / "state.json"
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        write_state_atomic(str(p), {"ts": "x"})
    assert os.listdir(tmp_path) == []          # neither the target nor a leaked .tmp


def test_safe_publish_success_returns_true(tmp_path):
    p = tmp_path / "state.json"
    assert safe_publish(str(p), {"ts": "x"}) is True
    assert json.loads(p.read_text()) == {"ts": "x"}


def test_safe_publish_swallows_write_failure_never_raises():
    # unwritable path -> False, no exception into the radio loop.
    assert safe_publish("/no/such/dir/state.json", {"ts": "x"}) is False


def test_safe_publish_swallows_serialization_failure(tmp_path):
    p = tmp_path / "state.json"
    assert safe_publish(str(p), {"bad": object()}) is False
    assert os.listdir(tmp_path) == []          # and no temp leaked on the serialize failure


def test_safe_publish_propagates_keyboardinterrupt(monkeypatch):
    # except Exception (not BaseException): KeyboardInterrupt/SystemExit must still escape.
    def boom(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(hb, "write_state_atomic", boom)
    with pytest.raises(KeyboardInterrupt):
        safe_publish("/x", {"ts": "x"})


def test_failure_log_rate_limited_to_one_on_persistent_failure(monkeypatch):
    logs = []
    monkeypatch.setattr(hb, "safe_publish", lambda p, s: False)
    pub = HeartbeatPublisher("/no/such/dir/state.json", log=logs.append)
    for _ in range(5):
        assert pub.publish({"ts": "x"}) is False
    assert len(logs) == 1                       # one transition-into-failure line, not five
    assert "failing" in logs[0].lower()


def test_log_fires_once_per_transition(monkeypatch):
    logs = []
    results = iter([False, False, True, True, False])   # fail, fail, recover, ok, fail
    monkeypatch.setattr(hb, "safe_publish", lambda p, s: next(results))
    pub = HeartbeatPublisher("/x", log=logs.append)
    for _ in range(5):
        pub.publish({"ts": "x"})
    assert len(logs) == 3                        # ->failing, ->recovered, ->failing
    assert "failing" in logs[0].lower()
    assert "recovered" in logs[1].lower()
    assert "failing" in logs[2].lower()


def test_publisher_never_raises_on_failure():
    # the wrapper itself must not raise even with a persistently bad path + no logger.
    pub = HeartbeatPublisher("/no/such/dir/state.json")
    assert pub.publish({"ts": "x"}) is False
