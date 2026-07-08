"""Host tests for the pure ingest core (observer registry + pipeline).

No radio/threads/file I-O — the sink is injected, so the decode -> record ->
stats -> dispatch pipeline is fully host-testable (Mac and Pi). The hardware
service (radio loop, queue writer, systemd) is integration-tested on the Pi.
"""
import json
import unittest

from ground.ingest.registry import ObserverRegistry
from ground.ingest.core import IngestCore
from ground.linkstats.linkstats import LinkStats

GOLDEN = b"V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12"


class TestObserverRegistry(unittest.TestCase):
    def test_dispatch_calls_all_in_order(self):
        r = ObserverRegistry()
        seen = []
        r.register(lambda x: seen.append(("a", x)))
        r.register(lambda x: seen.append(("b", x)))
        r.dispatch(123)
        self.assertEqual(seen, [("a", 123), ("b", 123)])

    def test_one_observer_error_does_not_break_others(self):
        r = ObserverRegistry()
        seen = []
        def _boom(_item):
            raise RuntimeError("boom")
        r.register(_boom)                 # a consumer that raises
        r.register(seen.append)
        r.dispatch(7)                 # must not propagate the observer's error
        self.assertEqual(seen, [7])   # the second observer still ran


class TestIngestCore(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.stats = LinkStats()
        self.reg = ObserverRegistry()
        self.dispatched = []
        self.reg.register(self.dispatched.append)
        self.core = IngestCore(sink=self.lines.append, stats=self.stats, registry=self.reg)

    def test_good_packet_logged_stats_dispatched(self):
        self.core.handle(rssi=-56, payload=GOLDEN, received_at="2026-07-07T00:00:00.000Z", mono=12.5)
        self.assertEqual(len(self.lines), 1)
        rec = json.loads(self.lines[0])
        self.assertEqual(rec["type"], "packet")
        self.assertEqual(rec["src"], 1)
        self.assertEqual(rec["raw"], GOLDEN.decode())          # raw preserved verbatim
        snap = self.stats.snapshot()
        self.assertIn((7, 1), snap)
        self.assertEqual(snap[(7, 1)]["rx"], 1)
        self.assertEqual(len(self.dispatched), 1)
        obs = self.dispatched[0]                                 # Observation(received_at, rssi, packet, mono)
        self.assertEqual(obs.received_at, "2026-07-07T00:00:00.000Z")
        self.assertEqual(obs.rssi, -56)
        self.assertEqual(obs.mono, 12.5)
        self.assertEqual(obs.packet.fields["SEQ"], 42)
        self.assertEqual(self.core.decoded, 1)

    def test_malformed_packet_logs_raw_no_stats_no_dispatch(self):
        self.core.handle(rssi=-60, payload=b"V:1 GARBAGE", received_at="2026-07-07T00:00:01.000Z")
        self.assertEqual(len(self.lines), 1)
        rec = json.loads(self.lines[0])
        self.assertEqual(rec.get("error"), "malformed-token")
        self.assertEqual(rec["raw"], "V:1 GARBAGE")            # raw kept for re-decode
        self.assertEqual(self.stats.snapshot(), {})            # no stats on error
        self.assertEqual(self.dispatched, [])                  # no dispatch on error
        self.assertEqual(self.core.errors, 1)

    def test_per_source_stats_accumulate(self):
        for seq in (10, 11, 13):  # one gap
            self.core.handle(-50, f"V:1 SYS:7 SRC:1 SEQ:{seq} ALT:0ft".encode(), "t")
        snap = self.stats.snapshot()[(7, 1)]
        self.assertEqual(snap["rx"], 3)
        self.assertEqual(snap["gaps"], 1)


class TestForeignTraffic(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.stats = LinkStats()
        self.reg = ObserverRegistry()
        self.dispatched = []
        self.reg.register(self.dispatched.append)
        self.core = IngestCore(self.lines.append, self.stats, self.reg)  # defaults SYS={7} SRC={1,2}

    def _events(self):
        recs = [json.loads(x) for x in self.lines]
        return [r for r in recs if r.get("type") == "event"]

    def test_foreign_sys_logged_as_event_not_stats(self):
        self.core.handle(-70, b"V:1 SYS:9 SRC:1 SEQ:1 ALT:0ft", "t")
        self.assertEqual(self.stats.snapshot(), {})          # never into stats
        self.assertEqual(self.dispatched, [])                # never dispatched
        self.assertEqual(self.core.decoded, 0)
        self.assertEqual(self.core.foreign.get(9), 1)        # counted per-SYS
        ev = self._events()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["event"], "foreign_sys")
        self.assertEqual(ev[0]["sys"], 9)
        self.assertEqual(ev[0]["raw"], "V:1 SYS:9 SRC:1 SEQ:1 ALT:0ft")  # raw preserved

    def test_unknown_src_flagged_as_anomaly(self):
        self.core.handle(-65, b"V:1 SYS:7 SRC:99 SEQ:1 ALT:0ft", "t")
        self.assertEqual(self.stats.snapshot(), {})
        self.assertEqual(self.dispatched, [])
        self.assertEqual(self.core.decoded, 0)
        self.assertEqual(self.core.anomalies.get((7, 99)), 1)
        ev = self._events()
        self.assertEqual(ev[0]["event"], "unknown_src")
        self.assertEqual((ev[0]["sys"], ev[0]["src"]), (7, 99))

    def test_none_of_foreign_garbage_anomaly_pollute_stats(self):
        self.core.handle(-70, b"V:1 SYS:9 SRC:1 SEQ:1 ALT:0ft", "t")     # foreign SYS
        self.core.handle(-71, b"V:1 GARBAGE", "t")                       # non-v1 garbage
        self.core.handle(-72, b"V:1 SYS:7 SRC:99 SEQ:1 ALT:0ft", "t")    # unknown SRC
        self.core.handle(-56, GOLDEN, "t")                               # good SYS:7 SRC:1
        snap = self.stats.snapshot()
        self.assertEqual(list(snap.keys()), [(7, 1)])        # ONLY the accepted packet
        self.assertEqual(snap[(7, 1)]["rx"], 1)
        self.assertEqual(len(self.dispatched), 1)


class TestCallsignId(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.stats = LinkStats()
        self.reg = ObserverRegistry()
        self.dispatched = []
        self.reg.register(self.dispatched.append)

    def _core(self, binding=None):
        return IngestCore(self.lines.append, self.stats, self.reg, callsign_binding=binding)

    def _events(self):
        return [json.loads(x) for x in self.lines if json.loads(x).get("type") == "event"]

    def test_call_emits_advisory_id_event(self):
        core = self._core()
        core.handle(-56, GOLDEN + b" CALL:KC3ZTQ", "t")
        self.assertEqual(core.decoded, 1)                # still an accepted packet
        self.assertIn((7, 1), self.stats.snapshot())
        ids = [e for e in self._events() if e["event"] == "id"]
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0]["callsign"], "KC3ZTQ")
        self.assertEqual((ids[0]["sys"], ids[0]["src"]), (7, 1))

    def test_no_call_no_id_event(self):
        core = self._core()
        core.handle(-56, GOLDEN, "t")
        self.assertEqual([e for e in self._events() if e["event"] == "id"], [])

    def test_binding_match_no_mismatch(self):
        core = self._core(binding={7: "KC3ZTQ"})
        core.handle(-56, GOLDEN + b" CALL:KC3ZTQ", "t")
        self.assertEqual(core.id_mismatches, {})
        self.assertEqual([e for e in self._events() if e["event"] == "id_mismatch"], [])

    def test_binding_mismatch_flagged(self):
        core = self._core(binding={7: "KC3ZTQ"})
        core.handle(-56, GOLDEN + b" CALL:W1AW", "t")
        self.assertEqual(core.id_mismatches.get((7, "W1AW")), 1)
        mm = [e for e in self._events() if e["event"] == "id_mismatch"]
        self.assertEqual(len(mm), 1)
        self.assertEqual((mm[0]["callsign"], mm[0]["expected"]), ("W1AW", "KC3ZTQ"))

    def test_foreign_sys_call_recorded_in_counter(self):
        core = self._core()
        core.handle(-70, b"V:1 SYS:9 SRC:1 SEQ:1 ALT:0ft CALL:N0CALL", "t")
        self.assertEqual(core.foreign.get(9), 1)
        self.assertIn("N0CALL", core.foreign_calls.get(9, set()))
        self.assertEqual(self.stats.snapshot(), {})      # still never into stats


if __name__ == "__main__":
    unittest.main()
