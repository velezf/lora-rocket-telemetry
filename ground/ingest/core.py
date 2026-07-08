"""Ingest pipeline core (pure): received payload -> log record + stats + fan-out.

The `sink` (a callable persisting one JSONL line) is injected, so the whole
decode -> policy -> record -> stats -> dispatch pipeline is host-testable with no
radio, threads, or files. The hardware service wires a queue-backed file writer
as the sink so the radio loop never blocks on disk (D1).

Foreign-traffic policy (addendum A):
- Only packets on a configured SYS (default {7}) and a known SRC (default {1,2})
  feed stats + fan-out.
- Valid-v1 packets on a FOREIGN SYS are counted per-SYS and logged as advisory
  `foreign_sys` events (raw preserved) — never into stats/dispatch/flights.
- Valid SYS but UNKNOWN SRC is flagged as an `unknown_src` anomaly (raw preserved),
  likewise kept out of stats/dispatch/flights.
SYS allowlist / known-SRC set are FIELD CONFIG (loaded by the service), not repo
constants — hence constructor params.
"""
from collections import namedtuple

from ground.decode.v1 import decode, DecodedPacket
from ground.sessionlog.records import packet_record, event_record, to_jsonl

# What consumers receive on the registry: the decoded packet plus the injected
# receive timestamp and RSSI (so live-flights / OLED / dashboard never read a clock).
Observation = namedtuple("Observation", "received_at rssi packet")


class IngestCore:
    def __init__(self, sink, stats, registry, allowed_sys=None, known_src=None,
                 callsign_binding=None):
        self._sink = sink            # callable(jsonl_line: str) -> None
        self._stats = stats          # LinkStats
        self._registry = registry    # ObserverRegistry
        self.allowed_sys = set(allowed_sys) if allowed_sys is not None else {7}
        self.known_src = set(known_src) if known_src is not None else {1, 2}
        self.callsign_binding = dict(callsign_binding) if callsign_binding else {}  # sys -> callsign
        self.decoded = 0             # accepted (our SYS + known SRC)
        self.errors = 0             # decode failures
        self.foreign = {}           # sys -> count (valid v1, foreign SYS)
        self.foreign_calls = {}     # sys -> set of callsigns seen on foreign traffic
        self.anomalies = {}         # (sys, src) -> count (our SYS, unknown SRC)
        self.id_mismatches = {}     # (sys, callsign) -> count (CALL != configured binding)

    def handle(self, rssi, payload, received_at):
        """Process one received frame. Always persists the raw (so history can be
        re-decoded, D1); only accepted traffic updates stats and fans out."""
        d = decode(payload)
        if not isinstance(d, DecodedPacket):
            self.errors += 1
            self._sink(to_jsonl({
                "type": "packet", "received_at": received_at, "rssi": rssi,
                "error": d.reason, "raw": d.raw,
            }))
            return

        f = d.fields
        sys = f.get("SYS")
        src = f.get("SRC")
        call = d.unknown.get("CALL")     # Part-97 station ID rides the unknown-tag path

        if sys not in self.allowed_sys:                      # foreign network
            self.foreign[sys] = self.foreign.get(sys, 0) + 1
            if call:
                self.foreign_calls.setdefault(sys, set()).add(call)
            self._sink(to_jsonl(event_record(received_at, "foreign_sys", sys=sys, callsign=call, raw=d.raw)))
            return

        if src not in self.known_src:                        # our SYS, unknown source
            self.anomalies[(sys, src)] = self.anomalies.get((sys, src), 0) + 1
            self._sink(to_jsonl(event_record(received_at, "unknown_src", sys=sys, src=src, callsign=call, raw=d.raw)))
            return

        # accepted: our SYS + known SRC
        self.decoded += 1
        self._sink(to_jsonl(packet_record(received_at, rssi, d)))
        if "SEQ" in f:
            self._stats.update(sys, src, f["SEQ"], rssi)
        self._registry.dispatch(Observation(received_at, rssi, d))

        if call:                                             # Part-97 ID audit trail
            self._sink(to_jsonl(event_record(received_at, "id", callsign=call, sys=sys, src=src)))
            expected = self.callsign_binding.get(sys)
            if expected is not None and expected != call:
                self.id_mismatches[(sys, call)] = self.id_mismatches.get((sys, call), 0) + 1
                self._sink(to_jsonl(event_record(
                    received_at, "id_mismatch", sys=sys, src=src, callsign=call, expected=expected)))
