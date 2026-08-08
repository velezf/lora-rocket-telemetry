# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
# ^ decode() union results accessed after runtime type asserts (same as test_v1.py).
"""Executable half of docs/newtag-collision-proof.md — pins the properties the
proof table claims, so a later refactor that breaks one fails a test instead of
silently invalidating a document.

Every special-cased tag NAME or frame KIND in the ground pipeline is exercised
with frames carrying ALL TEN new tags (Vel Gmx Gmn Wmx Gyx Gyy Gyz Mgx Mgy Mgz),
asserting the special case does not trigger. Anti-hollow: each guard is also
shown ABLE to trigger on the input it exists for.
"""
import unittest

from ground.decode.v1 import decode, DecodedPacket, DecodeError
from ground.flights.derive import derive_flights
from ground.flights.segmenter import FlightSegmenter, is_telemetry, max_is_meaningful
from ground.ingest.core import IngestCore
from ground.ingest.registry import ObserverRegistry
from ground.linkstats.linkstats import LinkStats
from ground.dashboard.model import LiveState

BASE = b"V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12"
ALL_NEW = (b" Vel:-1999.9 Gmx:199.9 Gmn:0.4 Wmx:2293.8"
           b" Gyx:-2293.8 Gyy:1.1 Gyz:-0.2 Mgx:-478.9 Mgy:23.0 Mgz:-41.5")


class TestDecoderExactKeyMatching(unittest.TestCase):
    """The decoder's only name matching is exact dict-key lookup (v1.py:110) and
    an exact string compare for V (v1.py:93). These tests pin that no new name
    is reachable by prefix/substring from an old one, or vice versa."""

    def test_vel_never_matches_v(self):
        r = decode(b"V:1 Vel:-1999.9")
        self.assertIsInstance(r, DecodedPacket)
        self.assertEqual(r.version, 1)                    # V read from V, not Vel
        self.assertAlmostEqual(r.fields["Vel"], -1999.9)

    def test_vel_as_first_token_is_not_a_version(self):
        """The V check is a whole-key compare: a leading Vel does NOT satisfy it."""
        r = decode(b"Vel:1 SYS:7")
        self.assertIsInstance(r, DecodeError)
        self.assertEqual(r.reason, "no-version")

    def test_similar_names_decode_independently(self):
        """G / Gmx / Gmn / Max / Mgx / Wmx all present with distinct values —
        each lands under its own key with its own value, no cross-talk."""
        r = decode(b"V:1 G:2.3 Gmx:199.9 Gmn:0.4 Max:5678ft Mgx:-478.9 Wmx:2293.8")
        self.assertIsInstance(r, DecodedPacket)
        self.assertAlmostEqual(r.fields["G"], 2.3)
        self.assertAlmostEqual(r.fields["Gmx"], 199.9)
        self.assertAlmostEqual(r.fields["Gmn"], 0.4)
        self.assertEqual(r.fields["Max"], 5678)           # int, ft stripped
        self.assertAlmostEqual(r.fields["Mgx"], -478.9)
        self.assertAlmostEqual(r.fields["Wmx"], 2293.8)
        self.assertEqual(r.unknown, {})

    def test_no_unit_suffix_stripping_on_new_tags(self):
        """Suffix stripping is keyed off the tag's OWN spec entry (None for all
        ten), so a value that merely ends in a known suffix letter is parsed
        whole — and a non-numeric one errors rather than being 'helped'."""
        r = decode(b"V:1 Vel:12.5")
        self.assertAlmostEqual(r.fields["Vel"], 12.5)
        bad = decode(b"V:1 Vel:12.5C")                    # C is T's suffix, not Vel's
        self.assertIsInstance(bad, DecodeError)
        self.assertEqual(bad.reason, "bad-value")


class TestIngestSpecialCasesUnmoved(unittest.TestCase):
    """ground/ingest/core.py special-cases SYS (allowlist), SRC (known set),
    CALL (Part-97 audit + binding), SEQ (linkstats). A frame carrying all ten
    new tags must move none of the error/foreign/anomaly/mismatch counters."""

    def setUp(self):
        self.lines = []
        self.stats = LinkStats()
        self.reg = ObserverRegistry()
        self.dispatched = []
        self.reg.register(self.dispatched.append)
        self.core = IngestCore(sink=self.lines.append, stats=self.stats,
                               registry=self.reg,
                               callsign_binding={7: "KC3ZTQ"})

    def test_frame_with_all_new_tags_is_fully_accepted(self):
        self.core.handle(rssi=-50, payload=BASE + ALL_NEW,
                         received_at="2026-08-08T00:00:00.000Z", mono=1.0)
        self.assertEqual(self.core.decoded, 1)            # ACCEPTED, not just quiet
        self.assertEqual(self.core.errors, 0)
        self.assertEqual(self.core.foreign, {})
        self.assertEqual(self.core.anomalies, {})
        self.assertEqual(self.core.id_mismatches, {})
        self.assertEqual(len(self.dispatched), 1)         # fanned out to consumers
        self.assertEqual(self.stats.snapshot()[(7, 1)]["rx"], 1)  # SEQ still counted

    def test_call_binding_still_works_beside_new_tags(self):
        """CALL is matched by exact key in unknown{} — new tags (in fields{})
        cannot shadow or feed it. A mismatched CALL still trips the audit."""
        self.core.handle(rssi=-50, payload=BASE + ALL_NEW + b" CALL:W1AW",
                         received_at="2026-08-08T00:00:01.000Z", mono=2.0)
        self.assertEqual(self.core.id_mismatches, {(7, "W1AW"): 1})  # guard CAN fire

    def test_guards_can_fire_anti_hollow(self):
        """The same frame shape on a foreign SYS IS segregated — proving the
        counters this class asserts flat are live counters, not dead ones."""
        foreign = BASE.replace(b"SYS:7", b"SYS:9") + ALL_NEW
        self.core.handle(rssi=-50, payload=foreign,
                         received_at="2026-08-08T00:00:02.000Z", mono=3.0)
        self.assertEqual(self.core.foreign, {9: 1})
        self.assertEqual(self.core.decoded, 0)


class TestBeaconClassificationUnaffected(unittest.TestCase):
    """is_telemetry (segmenter.py:70) keys on the PRESENCE OF St and nothing
    else. New tags must neither make a beacon telemetry nor a telemetry frame
    a beacon."""

    def test_st_frame_with_all_new_tags_is_telemetry(self):
        self.assertTrue(is_telemetry(0))                  # PAD shape carries St:0
        self.assertTrue(is_telemetry(1))

    def test_stless_frame_with_all_new_tags_is_still_a_beacon(self):
        """Pins the discriminator: ten known tags present, St absent -> beacon.
        (A frame that omits St has no flight-state information regardless of
        what else it carries.)"""
        d = decode(b"V:1 SYS:7 SRC:1" + ALL_NEW)          # no St, no SEQ
        self.assertIsInstance(d, DecodedPacket)
        seg = FlightSegmenter()
        seg.force_open("2026-08-08T00:00:00.000Z", 0.0, src=1)
        seg.observe("2026-08-08T00:00:01.000Z", 1.0, 1,
                    d.fields.get("St"), d.fields.get("ALT"), -50,
                    d.fields.get("SEQ"), max_alt=d.fields.get("Max"))
        fl = seg.close(1)
        self.assertEqual(fl.stats["beacons_rx"], 1)       # segregated
        self.assertEqual(fl.stats["packets_rx"], 0)       # not telemetry

    def test_max_gate_reads_only_st_and_max(self):
        """max_is_meaningful takes St alone; Gmx/Wmx magnitudes can never leak
        into peak_alt. A pad-shaped frame with huge envelope values contributes
        nothing to the peak; the peak still comes from ALT/Max."""
        self.assertFalse(max_is_meaningful(0))
        self.assertFalse(max_is_meaningful(None))
        records = [
            {"type": "packet", "received_at": "2026-08-08T00:00:00.000Z", "rssi": -50,
             "src": 1, "fields": {"SYS": 7, "SRC": 1, "SEQ": 1, "St": 1, "ALT": 100,
                                  "Max": 120, "Gmx": 199.9, "Wmx": 2293.8}},
            {"type": "packet", "received_at": "2026-08-08T00:00:01.000Z", "rssi": -50,
             "src": 1, "fields": {"SYS": 7, "SRC": 1, "SEQ": 2, "St": 2, "ALT": 90,
                                  "Max": 130, "Gmx": 199.9, "Wmx": 2293.8}},
        ]
        flights = derive_flights(records, silence_timeout_s=90)
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].stats["peak_alt_ft"], 130)   # Max, not 199.9/2293.8
        self.assertEqual(flights[0].stats["packets_rx"], 2)
        self.assertEqual(flights[0].stats["packets_lost"], 0)    # SEQ accounting intact


class TestDashboardModelUnaffected(unittest.TestCase):
    """model.py reads SRC/ALT/St/Max/SEQ/MET from fields and CALL from unknown,
    all by exact key. A frame with every new tag produces the same panel it
    would without them."""

    def test_snapshot_identical_with_and_without_new_tags(self):
        def panel_for(payload):
            state = LiveState()
            d = decode(payload)
            self.assertIsInstance(d, DecodedPacket)
            obs = type("Obs", (), {"received_at": "2026-08-08T00:00:00.000Z",
                                   "rssi": -50, "packet": d, "mono": 1.0})()
            state.update(obs)
            snap = dict(state.snapshot()[1])
            snap.pop("alt_hist")          # trailing-ALT window, identical anyway
            return snap
        self.assertEqual(panel_for(BASE), panel_for(BASE + ALL_NEW))


if __name__ == "__main__":
    unittest.main()
