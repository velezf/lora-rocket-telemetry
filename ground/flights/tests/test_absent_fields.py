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

   TWO DIFFERENT FRAMES trip this:
   - a TELEMETRY frame carrying `St` but missing `ALT`/`SEQ` (legal under ADR
     0001 — every tag is optional) reaches BOTH the live path and the rebuild,
     so both coalesced and both produced the wrong numbers. That is what
     TestLiveAndRebuildAgree drives.
   - a BARE `CALL` beacon carries no `St` at all. It used to reach only the live
     path (`derive.py` dropped it before segmentation), so the two paths counted
     differently. Resolved by policy — see below.

C. THE BEACON POLICY (decided 2026-08-02). Frames that are not telemetry do not
   participate in flight accounting: a beacon is counted in `beacons_rx`, never
   in `packets_rx`, and it neither extends `t_end` nor delays the silence
   timeout. `derive.py` no longer filters beacons out; the segregation lives in
   one place (segmenter.is_telemetry), so both paths now derive identical stats.
   TestBeaconsDoNotParticipateInFlightAccounting pins it.

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


def _live_closed_at(frames_at, tick_t):
    """Flights the LIVE path closed by a silence sweep at `tick_t`.

    `frames_at` is [(second, raw), ...] so a test can place frames on a real
    timeline — which is what the silence-timeout policy needs; the one-per-second
    helpers below are the common case expressed in terms of this one.
    """
    with tempfile.TemporaryDirectory() as d:
        snap = Path(d) / "snap.json"
        live = LiveFlights(lambda _ln: None, snap, silence_timeout_s=90)
        for t, raw in frames_at:
            live.on_observation(Observation(_ts(t), -60, decode(raw.encode()), float(t)))
        return live.tick(_ts(tick_t), float(tick_t))


def _rebuild_flights_at(frames_at):
    """Flights the OFFLINE REBUILD derives from the same timeline."""
    # every frame here is a valid v1 frame, so decode() returns DecodeOk; pyright
    # doesn't narrow the DecodeOk|DecodeError union through the comprehension.
    records = [packet_record(_ts(t), -60, decode(raw.encode()))  # pyright: ignore[reportArgumentType]
               for t, raw in frames_at]
    return derive_flights(records, silence_timeout_s=90)


def _at_one_hz(frames):
    return list(enumerate(frames))


def _live_closed(frames):
    """Flights the LIVE path closed after a long silence (advisory + snapshot)."""
    return _live_closed_at(_at_one_hz(frames), 200)


def _rebuild_flights(frames):
    """Flights the OFFLINE REBUILD derives — the canonical, published index."""
    return _rebuild_flights_at(_at_one_hz(frames))


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
    """A standalone `CALL` beacon under the decided policy.

    THE POLICY: frames that are not telemetry do not participate in flight
    accounting. This is the foreign-traffic rule (ground/ingest/core.py:12)
    applied to a second class of non-telemetry frame — counted and segregated,
    never merged. A beacon is evidence the RADIO is alive, not evidence about
    the flight.
    """

    def test_a_bare_beacon_carries_no_st_alt_or_seq(self):
        """The premise every other test in this class rests on."""
        d = decode(BARE_BEACON.encode())
        self.assertEqual(d.fields, {"SYS": 7, "SRC": 1})       # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(d.unknown, {"CALL": "KC3ZTQ"})        # pyright: ignore[reportAttributeAccessIssue]

    def test_a_bare_beacon_alone_opens_no_flight_on_either_path(self):
        """No `St`, so nothing that could read as ascent. A station identifying
        itself must never look like a launch."""
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


class TestBeaconsDoNotParticipateInFlightAccounting(unittest.TestCase):
    """The decided policy, pinned on BOTH paths.

    Supersedes the pinned live-vs-rebuild disagreement: the live path used to
    count a bare beacon in `packets_rx` (4 vs the rebuild's 2) and let a trailing
    beacon extend `t_end` (duration 3.0 vs 2.0). Both are now resolved the same
    way on both paths, so the two agree field for field.
    """

    # --- 1. packets_rx excludes beacons; beacons_rx counts them ---------------

    def test_a_beacon_does_not_enter_packets_rx(self):
        """Beacons carry no `SEQ`, so they cannot participate in loss accounting.
        In the denominator while absent from the sequence space, they would make
        the published loss percentage read artificially LOW."""
        self.assertEqual(_live_stats(_BEACON_FRAMES)["packets_rx"], 2)
        self.assertEqual(_rebuild_stats(_BEACON_FRAMES)["packets_rx"], 2)

    def test_a_beacon_is_visible_as_beacons_rx_not_discarded(self):
        self.assertEqual(_live_stats(_BEACON_FRAMES)["beacons_rx"], 2)
        self.assertEqual(_rebuild_stats(_BEACON_FRAMES)["beacons_rx"], 2)

    def test_a_flight_with_no_beacons_reports_zero_not_absent(self):
        """`beacons_rx` is always present — a consumer never has to distinguish
        "no beacons" from "this index predates the field"."""
        self.assertEqual(_live_stats(_FRAMES)["beacons_rx"], 0)
        self.assertEqual(_rebuild_stats(_FRAMES)["beacons_rx"], 0)

    def test_a_call_riding_on_a_telemetry_frame_is_still_telemetry(self):
        """The discriminator is the ABSENCE OF `St`, not the presence of `CALL`.
        `_FRAMES` carries two `St`-bearing frames that also carry `CALL`; those
        are telemetry and must stay in packets_rx. Of the three in-flight frames
        (boost + `St:2 CALL` + `St:2` telemetry) one is a CALL-rider, so a
        presence-of-CALL discriminator would report 2 here. GREEN before and
        after the policy — a regression guard on the discriminator, not a
        behaviour change."""
        self.assertEqual(_rebuild_stats(_FRAMES)["packets_rx"], 3)
        self.assertEqual(_live_stats(_FRAMES)["packets_rx"], 3)

    # --- 2. beacons do not extend t_end / delay the silence timeout -----------

    def test_a_trailing_beacon_does_not_extend_t_end(self):
        """A flight ends at its last TELEMETRY frame."""
        for stats in (_live_stats(_BEACON_FRAMES), _rebuild_stats(_BEACON_FRAMES)):
            self.assertEqual(stats["duration_s"], 2.0)

    def test_a_trailing_beacon_does_not_move_the_flights_t_end_timestamp(self):
        closed = _live_closed(_BEACON_FRAMES)
        self.assertEqual(closed[0].t_end, _ts(2))              # not _ts(3), the beacon
        self.assertEqual(_rebuild_flights(_BEACON_FRAMES)[0].t_end, _ts(2))

    def test_a_beacon_does_not_delay_the_silence_timeout(self):
        """THE FAILURE MODE THIS PREVENTS: a landed rocket beaconing every 60 s
        would never close — it would run until the battery died, and duration_s
        would become the interval between ID transmissions rather than the flight
        duration. The flight must not be defined by its callsign.

        Telemetry stops at t=1; beacons continue at 60/120/180. With a 90 s
        timeout the flight must close on the silence after t=1, not after t=180.
        """
        timeline = [(0, "V:1 SYS:7 SRC:1 SEQ:1 St:1 ALT:-80ft Max:-80ft"),
                    (1, "V:1 SYS:7 SRC:1 SEQ:2 St:2 ALT:-78ft Max:-74ft"),
                    (60, BARE_BEACON), (120, BARE_BEACON), (180, BARE_BEACON)]

        rebuilt = _rebuild_flights_at(timeline)
        self.assertEqual(len(rebuilt), 1)
        self.assertEqual(rebuilt[0].stats["duration_s"], 1.0)  # not 180.0
        self.assertEqual(rebuilt[0].t_end, _ts(1))
        # the t=60 beacon arrived while the flight was still open, so it counts;
        # the 120/180 ones postdate the close and belong to no flight.
        self.assertEqual(rebuilt[0].stats["beacons_rx"], 1)

        live = _live_closed_at(timeline[:3], 95)               # sweep at t=95
        self.assertEqual(len(live), 1)                         # the beacon at t=60
        self.assertEqual(live[0].stats["duration_s"], 1.0)     # did not hold it open
        self.assertEqual(live[0].stats["beacons_rx"], 1)

    # --- 3. beacons contribute to nothing else -------------------------------

    def test_a_beacon_contributes_no_rssi_to_the_flights_link_stats(self):
        """RSSI min/max describe the link to the VEHICLE during the flight. A
        beacon's RSSI is a fact about the radio, and merging it would widen the
        published spread with a sample the flight never produced."""
        timeline = [(0, "V:1 SYS:7 SRC:1 SEQ:1 St:1 ALT:-80ft Max:-80ft"),
                    (1, "V:1 SYS:7 SRC:1 SEQ:2 St:2 ALT:-78ft Max:-74ft")]
        with_beacon = _rebuild_flights_at(timeline + [(2, BARE_BEACON)])[0].stats
        without = _rebuild_flights_at(timeline)[0].stats
        self.assertEqual(with_beacon["rssi_min"], without["rssi_min"])
        self.assertEqual(with_beacon["rssi_max"], without["rssi_max"])

    def test_beacons_before_a_flight_opens_belong_to_no_flight(self):
        """A beacon on a quiet pad is not retro-counted into the flight that
        opens afterwards — it was not part of it."""
        timeline = [(0, BARE_BEACON), (1, BARE_BEACON),
                    (2, "V:1 SYS:7 SRC:1 SEQ:1 St:1 ALT:-80ft Max:-80ft")]
        self.assertEqual(_rebuild_flights_at(timeline)[0].stats["beacons_rx"], 0)
        self.assertEqual(_live_closed_at(timeline, 200)[0].stats["beacons_rx"], 0)

    # --- 4. and the two paths now agree --------------------------------------

    def test_live_and_rebuild_agree_on_a_bare_beacon(self):
        """RESOLVES the previously-pinned disagreement. The rebuild no longer
        drops beacons before segmentation and the live path no longer merges
        them: segregation happens in ONE place (the segmenter), so both paths
        derive identical stats — the published index and the live advisory
        events can no longer differ."""
        self.assertEqual(_live_stats(_BEACON_FRAMES), _rebuild_stats(_BEACON_FRAMES))


if __name__ == "__main__":
    unittest.main()
