"""Pure dashboard model — turns the Observation stream into a JSON-able view model.

`LiveState` keeps an IMMUTABLE per-SRC snapshot: each update() builds a new snapshot
and swaps the reference (atomic under the GIL), so a Flask reader grabs snapshot()
once per request and reads a frozen view — no locks, no torn reads, nothing mutated
in place. The trace is a BOUNDED tuple (a few minutes of packets), so nothing in the
live process grows unbounded. `view_model` assembles a snapshot + the LinkStats
snapshot + open-flight ids + ingest health. No Flask, no HTTP, no clock — host-tested.
"""
import json
from collections import deque

_STATE_NAMES = {0: "pad", 1: "ascent", 2: "descent"}


class EventsRing:
    """Bounded newest-first buffer of advisory event records, fed by teeing the log
    sink (flight_open/close, foreign_sys, unknown_src, id, service_*). Read-only view."""

    def __init__(self, maxlen: int = 8):
        self._events = deque(maxlen=maxlen)

    def capture(self, jsonl_line):
        try:
            rec = json.loads(jsonl_line)
        except (ValueError, TypeError):
            return
        if rec.get("type") == "event":
            self._events.append(rec)

    def recent(self):
        return list(reversed(self._events))     # newest first


class LiveState:
    def __init__(self, trace_len: int = 300, pad_len: int = 30):   # ~5 min trace at 1 Hz
        self._trace_len = trace_len
        self._pad_len = pad_len
        self._snapshot = {}     # immutable: {src: frozen per-src dict w/ bounded trace + pad tuples}

    def snapshot(self):
        """The current immutable snapshot. Readers grab this once; it is never mutated."""
        return self._snapshot

    def update(self, obs):
        """Registry consumer: obs = Observation(received_at, rssi, packet, mono).
        Builds a NEW snapshot and replaces the reference — never mutates in place."""
        f = obs.packet.fields
        src = f.get("SRC")
        if src is None:
            return
        prev = self._snapshot.get(src, {})
        call = obs.packet.unknown.get("CALL") or prev.get("callsign")
        alt = f.get("ALT")
        # one bounded trace holds both series (altitude + RSSI share the window)
        trace = (prev.get("trace", ()) + ((obs.received_at, alt, obs.rssi),))[-self._trace_len:]
        pad = prev.get("pad_window", ())
        if f.get("St") == 0:                # accumulate the pad baseline while on the pad
            pad = (pad + (alt,))[-self._pad_len:]
        per_src = {
            "src": src, "alt": alt, "peak": f.get("Max"), "st": f.get("St"),
            "rssi": obs.rssi, "seq": f.get("SEQ"), "met": f.get("MET"),
            "received_at": obs.received_at, "callsign": call, "trace": trace, "pad_window": pad,
        }
        self._snapshot = {**self._snapshot, src: per_src}

    def reset_baseline(self, src):
        """Clear a SRC's pad baseline (called on flight_close so the next pad period
        re-establishes AGL fresh). Replaces the snapshot — never mutates in place."""
        cur = self._snapshot.get(src)
        if cur is not None:
            self._snapshot = {**self._snapshot, src: {**cur, "pad_window": ()}}   # REPLACE, never mutate


def _stats_for_src(stats, src):
    for (_sys, s), v in stats.items():
        if s == src:
            return v
    return {}


def _baseline(cur):
    """Per-SRC pad baseline = mean of ALT sampled while St:0, or None if none yet."""
    valid = [a for a in cur.get("pad_window", ()) if a is not None]
    return (sum(valid) / len(valid)) if valid else None


def _agl(raw, base):
    if base is None or raw is None:
        return raw            # no baseline -> show raw altitude
    return round(raw - base)


def view_model(snapshot, stats, open_flights, health, events=()):
    """Assemble the dashboard payload from an immutable LiveState snapshot,
    LinkStats.snapshot() (keyed by (SYS,SRC)), {src: flight_id}, a health dict, and
    recent advisory events. Time-since-last-packet + T+ are computed client-side from
    received_at / met_s (no clock read here)."""
    panels = []
    operator = None
    for src in sorted(snapshot):
        cur = snapshot[src]
        st = _stats_for_src(stats, src)
        rx = st.get("rx", 0)
        gaps = st.get("gaps", 0)
        loss = round(100.0 * gaps / (rx + gaps), 1) if (rx + gaps) else 0.0
        base = _baseline(cur)
        if cur.get("callsign") and operator is None:
            operator = cur.get("callsign")
        panels.append({
            "src": src,
            "altitude_ft": _agl(cur.get("alt"), base),      # AGL (raw ALT - pad baseline)
            "peak_ft": _agl(cur.get("peak"), base),         # peak on AGL
            "baseline_ft": round(base) if base is not None else None,
            "state": _STATE_NAMES.get(cur.get("st"), "?"),
            "rssi": cur.get("rssi"),
            "seq_loss_pct": loss,
            "packets_rx": rx,
            "callsign": cur.get("callsign"),
            "flight_id": open_flights.get(src),
            "flight_open": src in open_flights,
            "met_s": cur.get("met"),
            "received_at": cur.get("received_at"),
            "trace": [{"t": t, "alt": a, "rssi": r} for t, a, r in cur.get("trace", ())],
        })
    return {"panels": panels, "callsign": operator, "events": list(events), "health": health}
