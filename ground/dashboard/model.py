"""Pure dashboard model — turns the Observation stream into a JSON-able view model.

`LiveState` keeps an IMMUTABLE per-SRC snapshot: each update() builds a new snapshot
and swaps the reference (atomic under the GIL), so a Flask reader grabs snapshot()
once per request and reads a frozen view — no locks, no torn reads, nothing mutated
in place. The trace is a BOUNDED tuple (a few minutes of packets), so nothing in the
live process grows unbounded.

AGL zero (v2): a bounded trailing window of recent ALT feeds the pure `pad_baseline`
(ground.flights.baseline). Before a flight the pad zero tracks the live quiet window
(so the pad reads ~0); at flight_open the baseline is LOCKED from the pre-boost window
and held through the flight; flight_close (reset_baseline) unlocks and clears it. Raw
ALT is never transformed. A frame carrying NO `St` (a Part-97 CALL beacon) is treated
as no information about flight state — it changes neither the lock nor the published
zero; absence is not "not in flight".

The published peak comes from the sled's `Max`, gated by `max_is_meaningful` imported
from ground.flights.segmenter — the single definition of when `Max` may be trusted
(never restated here). `view_model` assembles a snapshot + LinkStats + open-flight
ids + health. No Flask, no HTTP, no clock — host-tested.
"""
import json
from collections import deque

from ground.flights.baseline import pad_baseline, WINDOW, EXCLUDE_TAIL
from ground.flights.segmenter import max_is_meaningful

_STATE_NAMES = {0: "pad", 1: "ascent", 2: "descent"}
_HIST_LEN = WINDOW + EXCLUDE_TAIL     # enough trailing ALT for one baseline compute


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
    def __init__(self, trace_len: int = 300):   # ~5 min trace at 1 Hz
        self._trace_len = trace_len
        self._snapshot = {}     # immutable: {src: frozen per-src dict w/ bounded trace}

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
        st = f.get("St")
        trace = (prev.get("trace", ()) + ((obs.received_at, alt, obs.rssi),))[-self._trace_len:]
        hist = prev.get("alt_hist", ())
        locked = prev.get("locked_baseline")
        in_flight = st in (1, 2)
        # Lock the AGL zero at the transition into flight, from the PRE-boost window
        # (the current boost packet is appended only after this decision).
        if in_flight and locked is None:
            locked, _ = pad_baseline(list(hist))
        new_hist = (hist + (alt,))[-_HIST_LEN:]
        if st is None:
            # NO `St` = NO INFORMATION about flight state — never "not in flight".
            # A Part-97 CALL beacon (required every 10 min) carries no St; reading
            # its absence as pad UNLOCKED the baseline mid-flight and every later
            # altitude was then wrong by the whole baseline, permanently, with only
            # a blanked baseline_ft as the tell. So an St-less frame changes neither
            # the lock nor the published zero.
            baseline = prev.get("baseline")
        elif in_flight:
            baseline = locked                              # held through the flight
        else:
            locked = None                                  # on the pad -> unlocked
            baseline, _ = pad_baseline(list(new_hist))     # live pad zero (pad reads ~0)
        # `Max` is the sled's own running peak and is only trustworthy once St says it
        # has left the pad (the firmware sends Max:0 pre-launch and 0 ft is a legal
        # altitude, not a sentinel). The gate is IMPORTED from the segmenter — the
        # single definition — so this surface cannot drift from the flights index.
        peak = f.get("Max") if max_is_meaningful(st) else None
        per_src = {
            "src": src, "alt": alt, "peak": peak, "st": st,
            "rssi": obs.rssi, "seq": f.get("SEQ"), "met": f.get("MET"),
            "received_at": obs.received_at, "callsign": call, "trace": trace,
            "alt_hist": new_hist, "locked_baseline": locked, "baseline": baseline,
        }
        self._snapshot = {**self._snapshot, src: per_src}

    def reset_baseline(self, src):
        """Unlock + clear a SRC's AGL zero (called on flight_close so the next pad
        period re-establishes it fresh). Replaces the snapshot — never mutates."""
        cur = self._snapshot.get(src)
        if cur is not None:
            self._snapshot = {**self._snapshot, src: {
                **cur, "locked_baseline": None, "alt_hist": (), "baseline": None}}


def _stats_for_src(stats, src):
    for (_sys, s), v in stats.items():
        if s == src:
            return v
    return {}


def _agl(raw, base):
    if base is None or raw is None:
        return raw            # no baseline -> show raw altitude
    return round(raw - base)


def view_model(snapshot, stats, open_flights, health, events=()):
    """Assemble the dashboard payload from an immutable LiveState snapshot,
    LinkStats.snapshot() (keyed by (SYS,SRC)), {src: flight_id}, a health dict, and
    recent advisory events. Time-since-last-packet + T+ are computed client-side from
    received_at / met_s (no clock read here). AGL uses the snapshot's locked/live baseline."""
    panels = []
    operator = None
    for src in sorted(snapshot):
        cur = snapshot[src]
        st = _stats_for_src(stats, src)
        rx = st.get("rx", 0)
        gaps = st.get("gaps", 0)
        loss = round(100.0 * gaps / (rx + gaps), 1) if (rx + gaps) else 0.0
        base = cur.get("baseline")
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
