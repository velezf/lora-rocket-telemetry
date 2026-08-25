"""Derive the canonical flights index from the raw session log + the ops journal.

Index = pure function(session records, ops records). The session log is written
only by the service; the ops journal only by the CLI; the index only here (three
files, one writer each). Because both inputs are consumed on every rebuild, manual
annotations and manual open/close survive re-derivation and a future rule change
(D2's promise). Precedence: a manual close/open beats the silence timeout — a SRC
with a pending manual close is protected from silence auto-close until it fires.
"""
from datetime import datetime

from ground.flights.segmenter import FlightSegmenter


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _apply_annotations(flights, annotations):
    for a in annotations:
        for f in flights:
            if f.src == a["src"] and f.t_start <= a["at"] <= f.t_end:
                if a.get("label") is not None:
                    f.label = a["label"]
                if a.get("motor") is not None:
                    f.motor = a["motor"]
                if a.get("field") is not None:
                    f.field = a["field"]
                break


def derive_flights(session_records, ops=None, silence_timeout_s: float = 90):
    ops = ops or []
    annotations = [o for o in ops if o.get("op") == "annotate"]

    # pending manual closes per SRC (drive the silence-precedence protection)
    close_times = {}
    for o in ops:
        if o.get("op") == "close":
            close_times.setdefault(o["src"], []).append(_epoch(o["at"]))

    # merged, time-sorted event stream; at equal t: open(0) < packet(1) < close(2).
    # PACKET ORDER IS THE FILE'S APPEND ORDER, clamped monotonic (2026-08-25,
    # first 10 Hz field data): the session file's append order IS the physical
    # arrival order, but `received_at` wall stamps can invert by tens of ms.
    # A raw time-sort re-ordered such packets, and each backwards SEQ pair
    # became ~65,535 "lost" in the gap stat (F1 reported 720,906 lost from 11
    # inversions). Clamping each packet's sort key to running-max time makes
    # inverted stamps EQUAL keys, and Python's stable sort then preserves file
    # order — while ops events still interleave at their own timestamps.
    events = []
    t_mono = float("-inf")
    for r in session_records:
        # EVERY accepted packet reaches the segmenter, including non-telemetry
        # frames (bare `CALL` beacons, which carry no `St`). This filter used to
        # drop them here, which meant the rebuild counted differently from the
        # live path — the beacon segregation now lives in ONE place,
        # segmenter.is_telemetry, so the two cannot disagree.
        if r.get("type") == "packet" and "fields" in r:
            t_mono = max(t_mono, _epoch(r["received_at"]))
            events.append((t_mono, 1, "packet", r))
    for o in ops:
        if o.get("op") == "open":
            events.append((_epoch(o["at"]), 0, "open", o))
        elif o.get("op") == "close":
            events.append((_epoch(o["at"]), 2, "close", o))
    events.sort(key=lambda e: (e[0], e[1]))

    seg = FlightSegmenter(silence_timeout_s)
    flights = []
    for t, _, kind, obj in events:
        protect = frozenset(src for src, ts in close_times.items() if any(tc >= t for tc in ts))
        flights.extend(seg.check_timeouts(t, protect))
        if kind == "packet":
            f = obj["fields"]
            # Absent tags stay absent — same contract as the live path
            # (ground/flights/live.py), so rebuild and live derive the same stats.
            seg.observe(obj["received_at"], t, obj.get("src"), f.get("St"),
                        f.get("ALT"), obj.get("rssi"), f.get("SEQ"),
                        max_alt=f.get("Max"))
        elif kind == "open":
            seg.force_open(obj["at"], t, obj["src"])
        elif kind == "close":
            fl = seg.close(obj["src"])
            if fl:
                flights.append(fl)
            close_times[obj["src"]].remove(t)        # consumed — stops protecting
            if not close_times[obj["src"]]:
                del close_times[obj["src"]]

    for src in seg.open_srcs():
        flights.append(seg.close(src))

    _apply_annotations(flights, annotations)
    return flights
