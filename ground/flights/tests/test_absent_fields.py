"""One defect shape, two symptoms: a sentinel colliding with a legal value.

The v1 wire format cannot say ABSENT distinctly from ZERO, and 0 is a legal
value for every field that matters here (altitude AGL-relative, sequence, peak).
Two consequences this module pins down:

A. The sled transmits its OWN running peak as `Max` in every packet, so a single
   post-apogee frame restores the true peak after a dropped packet near apogee.
   But the firmware sends `Max:0` on the pad, and 0 ft is an altitude, not a
   sentinel — trusting a pad `Max` publishes a peak that is baseline-high (F1's
   pad sits at -84 ft, so a naive max(Max) would publish +84 ft AGL for a flight
   that reached 10 ft). `Max` counts only once St has left the pad.

B. A frame legitimately missing `ALT`/`SEQ` must contribute nothing to the fields
   it cannot supply. Coalescing None -> 0 fabricated a 65535-packet loss (the
   uint16 gap arithmetic wraps) and a 0 ft peak, and poisoned the pad baseline
   window with a 0 ft sample.

   TWO DIFFERENT FRAMES trip this, and they do NOT reach the same code:
   - a TELEMETRY frame carrying `St` but missing `ALT`/`SEQ` (legal under ADR
     0001 — every tag is optional) reaches BOTH the live path and the rebuild,
     so both coalesced and both produced the wrong numbers. That is what
     TestLiveAndRebuildAgree drives.
   - a BARE `CALL` beacon carries no `St` at all, so `derive.py`'s record filter
     drops it before segmentation: the rebuild was never exposed, and the
     corruption was LIVE-PATH ONLY. See TestBareCallBeacon, which pins that
     asymmetry rather than assuming it.

The live path and the offline rebuild must agree — rebuild is what regenerates
the published index, so a disagreement is a published wrong number.
"""
import tempfile
import unittest
from pathlib import Path

from ground.decode.v1 import decode
from ground.flights.derive import derive_flights
from ground.flights.live import LiveFlights
from ground.flights.segmenter import FlightSegmenter, _peak_candidates, max_is_meaningful
from ground.ingest.core import Observation
from ground.sessionlog.records import packet_record


def _ts(sec):
    return f"2026-07-08T00:{sec // 60:02d}:{sec % 60:02d}.000Z"


class TestMaxIsMeaningful(unittest.TestCase):
    """The ONE definition of when the sled's `Max` may be trusted.

    Pinned directly, independently of the segmenter, because it has more than one
    consumer: the flights index (here) and the dashboard/OLED view model. Two
    copies of this `St` check in two files is exactly how a third, disagreeing
    definition gets created — so this contract is tested on its own terms.
    """

    def test_pad_max_is_the_prelaunch_sentinel(self):
        self.assertFalse(max_is_meaningful(0))

    def test_max_is_meaningful_during_ascent(self):
        self.assertTrue(max_is_meaningful(1))

    def test_max_is_meaningful_during_descent(self):
        """Descent is where `Max` earns its keep — it is the apogee readout."""
        self.assertTrue(max_is_meaningful(2))

    def test_an_absent_st_is_not_trusted(self):
        """No `St` (a bare CALL beacon) -> nothing says the sled has left the pad."""
        self.assertFalse(max_is_meaningful(None))

    def test_it_is_the_only_implementation_the_segmenter_uses(self):
        """_peak_candidates must delegate, not restate — one implementation."""
        self.assertEqual(_peak_candidates(0, -83, 0), [-83])        # pad Max dropped
        self.assertEqual(_peak_candidates(2, -83, 0), [-83, 0])     # in flight, Max kept


class TestSledMaxIsTheAuthorityOnPeak(unittest.TestCase):
    """Defect A — the ground recomputed the peak from received ALT alone."""

    def test_sled_max_recovers_a_peak_lost_to_a_dropped_packet(self):
        seg = FlightSegmenter(silence_timeout_s=90)
        seg.observe(_ts(0), 0.0, 1, 1, 100, -60, 1, max_alt=100)
        # the apogee frame (ALT 900) never arrived; the next one carries Max:900
        seg.observe(_ts(2), 2.0, 1, 2, 800, -60, 3, max_alt=900)
        fl = seg.close(1)
        assert fl is not None
        self.assertEqual(fl.stats["peak_alt_ft"], 900)

    def test_pad_max_sentinel_never_raises_the_peak(self):
        """`Max:0` on the pad is the trap: it is bigger than every real F1
        altitude, so an ungated max(Max) publishes the pad, not the flight."""
        seg = FlightSegmenter(silence_timeout_s=90)
        seg.observe(_ts(0), 0.0, 1, 0, -83, -60, 0, max_alt=0)     # pad — no flight
        seg.observe(_ts(1), 1.0, 1, 1, -80, -60, 1, max_alt=-80)   # boost
        seg.observe(_ts(2), 2.0, 1, 2, -75, -60, 2, max_alt=-74)   # true peak, ALT frame lost
        seg.observe(_ts(3), 3.0, 1, 0, -83, -60, 3, max_alt=0)     # pad-coded frame mid-flight
        fl = seg.close(1)
        assert fl is not None
        self.assertEqual(fl.stats["peak_alt_ft"], -74)   # not -75 (ALT only), not 0 (pad Max)


class TestAbsentIsNotZero(unittest.TestCase):
    """Defect B — the segmenter must skip what a frame cannot supply."""

    def _flight_with_an_altless_frame(self):
        seg = FlightSegmenter(silence_timeout_s=90)
        seg.observe(_ts(0), 0.0, 1, 1, -80, -60, 1, max_alt=-80)
        seg.observe(_ts(1), 1.0, 1, 2, -74, -60, 2, max_alt=-74)
        seg.observe(_ts(2), 2.0, 1, 2, None, -60, None)      # no ALT, no SEQ
        seg.observe(_ts(3), 3.0, 1, 2, -76, -60, 3, max_alt=-74)
        fl = seg.close(1)
        assert fl is not None
        return fl

    def test_absent_alt_does_not_collapse_the_peak_to_zero(self):
        self.assertEqual(self._flight_with_an_altless_frame().stats["peak_alt_ft"], -74)

    def test_absent_seq_does_not_fabricate_a_uint16_wrap_of_loss(self):
        self.assertEqual(self._flight_with_an_altless_frame().stats["packets_lost"], 0)

    def test_an_altless_frame_is_still_a_received_packet(self):
        self.assertEqual(self._flight_with_an_altless_frame().stats["packets_rx"], 4)

    def test_seq_resumes_from_the_last_real_seq_across_an_seqless_frame(self):
        """A frame with no SEQ consumed no sequence number, so the gap either
        side of it is measured between the real SEQs — 5 after 2 is two missing."""
        seg = FlightSegmenter(silence_timeout_s=90)
        seg.observe(_ts(0), 0.0, 1, 1, 100, -60, 2, max_alt=100)
        seg.observe(_ts(1), 1.0, 1, 2, 90, -60, None)         # no SEQ
        seg.observe(_ts(2), 2.0, 1, 2, 80, -60, 5, max_alt=100)
        fl = seg.close(1)
        assert fl is not None
        self.assertEqual(fl.stats["packets_lost"], 2)

    def test_a_flight_that_never_saw_an_altitude_reports_no_peak(self):
        """No ALT ever received -> peak is unknown, not 0 ft."""
        seg = FlightSegmenter(silence_timeout_s=90)
        seg.observe(_ts(0), 0.0, 1, 1, None, -60, None)
        fl = seg.close(1)
        assert fl is not None
        self.assertIsNone(fl.stats["peak_alt_ft"])

    def test_observe_is_atomic_no_field_advances_if_another_raises(self):
        """Compute-then-commit: a raise inside observe() must leave the working
        flight exactly as it was, never half-updated."""
        seg = FlightSegmenter(silence_timeout_s=90)
        seg.observe(_ts(0), 0.0, 1, 1, 100, -60, 1, max_alt=100)

        class Poison(int):
            def __sub__(self, other):
                raise RuntimeError("boom")

            __rsub__ = __sub__

        with self.assertRaises(RuntimeError):
            seg.observe(_ts(1), 1.0, 1, 2, 500, -60, Poison(2), max_alt=500)
        fl = seg.close(1)
        assert fl is not None
        self.assertEqual(fl.stats["packets_rx"], 1)          # not 2
        self.assertEqual(fl.stats["peak_alt_ft"], 100)       # not 500
        self.assertEqual(fl.t_end, _ts(0))                   # not _ts(1)


# --- driving the same frames down both paths ----------------------------------

BARE_BEACON = "V:1 SYS:7 SRC:1 CALL:KC3ZTQ"
"""A STANDALONE Part-97 identification beacon: `CALL` and nothing else.

Distinct from how every other test in the repo models `CALL` — as a rider on a
complete telemetry frame (`GOLDEN + b" CALL:KC3ZTQ"` in ground/ingest/tests and
ground/decode/tests). A rider exercises none of this: it still carries `St`,
`ALT` and `SEQ`. The bare form carries no `St`, so it is the frame the flights
code had never once been tested against.
"""


def _live_closed(frames):
    """Flights the LIVE path closed after a long silence (advisory + snapshot)."""
    with tempfile.TemporaryDirectory() as d:
        snap = Path(d) / "snap.json"
        live = LiveFlights(lambda _ln: None, snap, silence_timeout_s=90)
        for i, raw in enumerate(frames):
            live.on_observation(Observation(_ts(i), -60, decode(raw.encode()), float(i)))
        return live.tick(_ts(200), 200.0)


def _rebuild_flights(frames):
    """Flights the OFFLINE REBUILD derives — the canonical, published index."""
    # every frame here is a valid v1 frame, so decode() returns DecodeOk; pyright
    # doesn't narrow the DecodeOk|DecodeError union through the comprehension.
    records = [packet_record(_ts(i), -60, decode(raw.encode()))  # pyright: ignore[reportArgumentType]
               for i, raw in enumerate(frames)]
    return derive_flights(records, silence_timeout_s=90)


def _live_stats(frames):
    closed = _live_closed(frames)
    assert len(closed) == 1, closed
    return closed[0].stats


def _rebuild_stats(frames):
    flights = _rebuild_flights(frames)
    assert len(flights) == 1, flights
    return flights[0].stats


# One frame per second, so the live monotonic clock and the rebuild's wall-clock
# epoch advance identically and the two paths are comparable field by field:
# 16 quiet pad frames, an St-BEARING frame with no ALT/SEQ, two more pad frames
# (the excluded pre-boost tail), boost, another St-bearing ALT-less frame
# mid-flight, then a post-apogee frame whose ALT is below the sled's own Max.
#
# Every frame here carries `St`, so every frame reaches BOTH paths — that is what
# makes a field-by-field comparison meaningful.
_FRAMES = (
    [f"V:1 SYS:7 SRC:1 SEQ:{s} St:0 ALT:-83ft Max:0ft" for s in range(16)]
    + ["V:1 SYS:7 SRC:1 St:0 CALL:KK7ABC"]
    + [f"V:1 SYS:7 SRC:1 SEQ:{s} St:0 ALT:-83ft Max:0ft" for s in (16, 17)]
    + ["V:1 SYS:7 SRC:1 SEQ:18 St:1 ALT:-80ft Max:-80ft",
       "V:1 SYS:7 SRC:1 St:2 CALL:KK7ABC",
       "V:1 SYS:7 SRC:1 SEQ:19 St:2 ALT:-78ft Max:-74ft"]
)


class TestLiveAndRebuildAgree(unittest.TestCase):
    """St-bearing frames missing ALT/SEQ — legal under ADR 0001, since every tag
    is optional. These DO reach both paths, and both call sites coalesced
    None -> 0. Fixing only one would make the live advisory events disagree with
    the index that actually gets published."""

    def test_live_peak_is_the_sled_max_not_zero(self):
        self.assertEqual(_live_stats(_FRAMES)["peak_alt_ft"], -74)

    def test_live_altless_frame_does_not_fabricate_lost_packets(self):
        self.assertEqual(_live_stats(_FRAMES)["packets_lost"], 0)

    def test_rebuild_peak_is_the_sled_max_not_zero(self):
        self.assertEqual(_rebuild_stats(_FRAMES)["peak_alt_ft"], -74)

    def test_rebuild_altless_frame_does_not_fabricate_lost_packets(self):
        self.assertEqual(_rebuild_stats(_FRAMES)["packets_lost"], 0)

    def test_an_altless_frame_does_not_poison_the_pad_baseline(self):
        """A 0 ft sample among -83 ft pad reads blows the stability gate, so the
        baseline goes None and the flight loses its AGL zero entirely."""
        self.assertEqual(_rebuild_stats(_FRAMES)["baseline_ft"], -83)
        self.assertEqual(_rebuild_stats(_FRAMES)["baseline_n"], 15)

    def test_live_and_rebuild_derive_identical_stats(self):
        self.assertEqual(_live_stats(_FRAMES), _rebuild_stats(_FRAMES))


# --- the bare CALL beacon: never tested before, and the paths differ -----------

# boost, a bare beacon, telemetry, then a trailing bare beacon. The trailing one
# is what exposes the t_end/duration difference between the two paths. Altitudes
# are F1-shaped (negative raw, below a negative pad baseline) because that is
# what made the old coalesced 0 the MAXIMUM rather than a harmless low sample.
_BEACON_FRAMES = [
    "V:1 SYS:7 SRC:1 SEQ:1 St:1 ALT:-80ft Max:-80ft",
    BARE_BEACON,
    "V:1 SYS:7 SRC:1 SEQ:2 St:2 ALT:-78ft Max:-74ft",
    BARE_BEACON,
]


class TestBareCallBeacon(unittest.TestCase):
    """Pins the CURRENT, POST-FIX behaviour of a standalone `CALL` beacon.

    These tests assert what the code DOES, not what it should do. The two paths
    do not treat a bare beacon alike, and that difference is deliberately left
    unresolved here — see test_live_and_rebuild_disagree_on_a_bare_beacon.
    """

    def test_a_bare_beacon_carries_no_st_alt_or_seq(self):
        """The premise every other test in this class rests on."""
        d = decode(BARE_BEACON.encode())
        self.assertEqual(d.fields, {"SYS": 7, "SRC": 1})       # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(d.unknown, {"CALL": "KC3ZTQ"})        # pyright: ignore[reportAttributeAccessIssue]

    def test_a_bare_beacon_alone_opens_no_flight_on_either_path(self):
        """No `St`, so nothing that could read as ascent."""
        self.assertEqual(_live_closed([BARE_BEACON, BARE_BEACON]), [])
        self.assertEqual(_rebuild_flights([BARE_BEACON, BARE_BEACON]), [])

    def test_a_bare_beacon_corrupts_no_live_stat(self):
        """The live path DOES segment a bare beacon (it has no `St` filter), so
        this is the case the coalescing actually corrupted. Replaying these exact
        frames through the OLD call site yields peak_alt_ft 0 (the coalesced 0
        outranks every real F1-shaped altitude) and packets_lost 131068 — two
        beacons, each wrapping the uint16 gap arithmetic. Post-fix, intact:"""
        stats = _live_stats(_BEACON_FRAMES)
        self.assertEqual(stats["peak_alt_ft"], -74)            # the sled's own Max
        self.assertEqual(stats["packets_lost"], 0)

    def test_the_rebuild_never_sees_a_bare_beacon_at_all(self):
        """`derive.py` admits only records whose fields carry `St`, so a bare
        beacon is dropped before segmentation — the rebuild was never exposed to
        this defect, and its numbers count telemetry frames only."""
        stats = _rebuild_stats(_BEACON_FRAMES)
        self.assertEqual(stats["packets_rx"], 2)               # the 2 telemetry frames
        self.assertEqual(stats["peak_alt_ft"], -74)
        self.assertEqual(stats["packets_lost"], 0)

    def test_live_and_rebuild_disagree_on_a_bare_beacon(self):
        """DELIBERATE, UNRESOLVED — do not "fix" this to make it pass differently.

        Whether a beacon counts as a packet OF THE FLIGHT is a product question,
        not a bug: the live path counts it in packets_rx and lets it extend the
        flight's t_end (and so hold off the silence timeout), while the rebuild
        drops it entirely. Resolving it needs a human call. This test exists so
        the difference is documented and cannot drift silently.
        """
        live, rebuild = _live_stats(_BEACON_FRAMES), _rebuild_stats(_BEACON_FRAMES)
        self.assertEqual(live["packets_rx"], 4)                # beacons counted
        self.assertEqual(rebuild["packets_rx"], 2)             # beacons dropped
        self.assertEqual(live["duration_s"], 3.0)              # trailing beacon extends t_end
        self.assertEqual(rebuild["duration_s"], 2.0)           # ends at the last telemetry frame
        self.assertNotEqual(live, rebuild)                     # the published index differs


if __name__ == "__main__":
    unittest.main()
