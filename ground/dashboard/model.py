"""Pure dashboard model — turns the Observation stream into a JSON-able view model.

`LiveState` keeps an IMMUTABLE per-SRC snapshot: each update() builds a new snapshot
and swaps the reference (atomic under the GIL), so a Flask reader grabs snapshot()
once per request and reads a frozen view — no locks, no torn reads, nothing mutated
in place. The trace is a BOUNDED tuple (a few minutes of packets), so nothing in the
live process grows unbounded. `view_model` assembles a snapshot + the LinkStats
snapshot + open-flight ids + ingest health. No Flask, no HTTP, no clock — host-tested.
"""
_STATE_NAMES = {0: "pad", 1: "ascent", 2: "descent"}


class LiveState:
    def __init__(self, trace_len: int = 300):   # ~5 min at 1 Hz
        self._trace_len = trace_len
        self._snapshot = {}     # immutable: {src: frozen per-src dict w/ a bounded trace tuple}

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
        trace = (prev.get("trace", ()) + ((obs.received_at, f.get("ALT")),))[-self._trace_len:]
        per_src = {
            "src": src, "alt": f.get("ALT"), "peak": f.get("Max"), "st": f.get("St"),
            "rssi": obs.rssi, "seq": f.get("SEQ"), "received_at": obs.received_at,
            "callsign": call, "trace": trace,
        }
        self._snapshot = {**self._snapshot, src: per_src}   # REPLACE, never mutate


def _stats_for_src(stats, src):
    for (_sys, s), v in stats.items():
        if s == src:
            return v
    return {}


def view_model(snapshot, stats, open_flights, health):
    """Assemble the dashboard payload from an immutable LiveState snapshot,
    LinkStats.snapshot() (keyed by (SYS,SRC)), {src: flight_id}, and a health dict."""
    panels = []
    for src in sorted(snapshot):
        cur = snapshot[src]
        st = _stats_for_src(stats, src)
        rx = st.get("rx", 0)
        gaps = st.get("gaps", 0)
        loss = round(100.0 * gaps / (rx + gaps), 1) if (rx + gaps) else 0.0
        panels.append({
            "src": src,
            "altitude_ft": cur.get("alt"),
            "peak_ft": cur.get("peak"),
            "state": _STATE_NAMES.get(cur.get("st"), "?"),
            "rssi": cur.get("rssi"),
            "seq_loss_pct": loss,
            "packets_rx": rx,
            "callsign": cur.get("callsign"),
            "flight_id": open_flights.get(src),
            "flight_open": src in open_flights,
            "trace": [{"t": t, "alt": a} for t, a in cur.get("trace", ())],
        })
    return {"panels": panels, "health": health}
