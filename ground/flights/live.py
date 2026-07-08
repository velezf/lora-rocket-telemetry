"""Live flight detection — an ingest consumer that emits flight_open/flight_close
advisory events and persists a disposable index snapshot (closed flights only).

Time is INJECTED: every method takes the loop-stamped wall `received_at` (what gets
RECORDED) and a `mono` monotonic value (silence/duration arithmetic) — nothing here
reads a clock, and the silence sweep is immune to wall-clock steps (NTP/RTC jumps).
The canonical index comes from rebuild(session, ops); this snapshot is a regenerable
single-writer cache. On shutdown the caller runs one final tick; any still-open
flight is LEFT OPEN (not in the snapshot) and resolved by the canonical rebuild.
"""
from pathlib import Path

from ground.flights.segmenter import FlightSegmenter
from ground.flights.flights import flights_to_json
from ground.sessionlog.records import event_record, to_jsonl


class LiveFlights:
    def __init__(self, sink, snapshot_path, silence_timeout_s: float = 90):
        self._sink = sink
        self._snapshot = Path(snapshot_path)
        self._seg = FlightSegmenter(silence_timeout_s)
        self._closed = []

    def open_srcs(self):
        return self._seg.open_srcs()

    def open_flight_ids(self):
        """{src: flight_id} for currently-open flights (for the dashboard/OLED)."""
        return self._seg.open_flight_ids()

    def on_observation(self, obs):
        """Registry consumer: obs = Observation(received_at, rssi, packet, mono).
        Records use the wall `received_at`; silence/duration use `mono`."""
        f = obs.packet.fields
        opened = self._seg.observe(
            obs.received_at, obs.mono, f.get("SRC"), f.get("St"),
            f.get("ALT") if f.get("ALT") is not None else 0,
            obs.rssi, f.get("SEQ") if f.get("SEQ") is not None else 0)
        if opened:
            self._sink(to_jsonl(event_record(obs.received_at, "flight_open",
                                             flight_id=opened, src=f.get("SRC"))))

    def tick(self, now_iso, mono):
        """Cheap, step-immune silence sweep: `mono` drives the timeout; `now_iso`
        is only the wall time recorded on any flight_close event."""
        closed = self._seg.check_timeouts(mono)
        for fl in closed:
            self._closed.append(fl)
            self._sink(to_jsonl(event_record(now_iso, "flight_close",
                                             flight_id=fl.flight_id, src=fl.src, stats=fl.stats)))
        if closed:
            self._snapshot.write_text(flights_to_json(self._closed))
