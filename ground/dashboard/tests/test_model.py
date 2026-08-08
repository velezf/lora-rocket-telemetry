"""Host tests for the pure dashboard model — LiveState (immutable snapshots) + view_model.

Pure functions: an Observation stream in, a JSON-able view model out. No Flask, no
HTTP, no clock. The thin Flask/HTTP shell is Pi-only and not tested here.
"""
import unittest

from ground.dashboard.model import LiveState, view_model, EventsRing
from ground.ingest.core import Observation
from ground.decode.v1 import decode


def obs(received_at, src, st, alt, peak, seq, rssi=-60, call=None, met=None):
    pkt = f"V:1 SYS:7 SRC:{src} SEQ:{seq} St:{st} ALT:{alt}ft Max:{peak}ft"
    if met is not None:
        pkt += f" MET:{met}"
    if call:
        pkt += f" CALL:{call}"
    # mono rides SEQ: the fixtures send one packet per second, so the sequence
    # number doubles as the monotonic clock the time-based baseline window reads.
    return Observation(received_at, rssi, decode(pkt.encode()), float(seq))


def beacon(received_at, src, call="KC3ZTQ", rssi=-60):
    """A bare Part-97 station-ID frame: no St, no ALT, no Max, no SEQ."""
    pkt = f"V:1 SYS:7 SRC:{src} CALL:{call}"
    return Observation(received_at, rssi, decode(pkt.encode()), 0.0)


class TestLiveState(unittest.TestCase):
    def test_tracks_current_per_src(self):
        s = LiveState()
        s.update(obs("t1", 1, 1, 100, 100, 1, rssi=-50))
        s.update(obs("t2", 1, 2, 80, 120, 2, rssi=-55))
        cur = s.snapshot()[1]
        self.assertEqual((cur["alt"], cur["peak"], cur["st"], cur["rssi"], cur["seq"]),
                         (80, 120, 2, -55, 2))

    def test_multi_src_independent(self):
        s = LiveState()
        s.update(obs("t1", 1, 1, 100, 100, 1))
        s.update(obs("t2", 2, 1, 900, 900, 1))
        snap = s.snapshot()
        self.assertEqual(sorted(snap), [1, 2])
        self.assertEqual((snap[1]["alt"], snap[2]["alt"]), (100, 900))

    def test_callsign_sticky(self):
        s = LiveState()
        s.update(obs("t1", 1, 1, 100, 100, 1, call="KC3ZTQ"))
        s.update(obs("t2", 1, 1, 110, 110, 2))
        self.assertEqual(s.snapshot()[1]["callsign"], "KC3ZTQ")

    def test_snapshot_replaced_not_mutated(self):
        s = LiveState()
        s.update(obs("t1", 1, 1, 100, 100, 1))
        snap1 = s.snapshot()
        s.update(obs("t2", 1, 1, 200, 200, 2))
        snap2 = s.snapshot()
        self.assertIsNot(snap1, snap2)            # top-level reference replaced
        self.assertIsNot(snap1[1], snap2[1])      # per-src object replaced
        self.assertEqual(snap1[1]["alt"], 100)    # the earlier snapshot is frozen
        self.assertEqual(snap2[1]["alt"], 200)

    def test_trace_is_bounded(self):
        s = LiveState(trace_len=3)
        for i in range(5):
            s.update(obs(f"t{i}", 1, 1, i * 10, i * 10, i))
        trace = s.snapshot()[1]["trace"]
        self.assertEqual(len(trace), 3)
        self.assertEqual([a for _, a, _r in trace], [20, 30, 40])   # (t, alt, rssi), bounded


class TestViewModel(unittest.TestCase):
    def test_panels_and_loss(self):
        s = LiveState()
        s.update(obs("t1", 1, 1, 100, 500, 1, rssi=-50, call="KC3ZTQ"))
        stats = {(7, 1): {"rx": 9, "gaps": 1, "rssi_min": -60, "rssi_max": -50}}
        health = {"session": "session-x.jsonl", "uptime_s": 42, "crc_errors": 2}
        vm = view_model(s.snapshot(), stats, open_flights={1: "2026-07-08-F1"}, health=health)
        self.assertEqual(vm["health"], health)
        p = next(pnl for pnl in vm["panels"] if pnl["src"] == 1)
        self.assertEqual((p["altitude_ft"], p["peak_ft"], p["state"], p["rssi"]),
                         (100, 500, "ascent", -50))
        self.assertEqual((p["packets_rx"], p["seq_loss_pct"]), (9, 10.0))
        self.assertEqual((p["callsign"], p["flight_id"], p["flight_open"]),
                         ("KC3ZTQ", "2026-07-08-F1", True))

    def test_agl_baseline_pad_zero_boost_relative(self):
        s = LiveState()
        for i in range(4):                          # on the pad (St:0) at ALT -96 -> baseline -96
            s.update(obs(f"p{i}", 1, 0, -96, -96, i))
        pad_panel = view_model(s.snapshot(), {}, {}, {})["panels"][0]
        self.assertEqual(pad_panel["altitude_ft"], 0)     # AGL on the pad
        self.assertEqual(pad_panel["baseline_ft"], -96)
        s.update(obs("boost", 1, 1, 404, 404, 5))         # boost: raw ALT 404, Max 404
        p = view_model(s.snapshot(), {}, {}, {})["panels"][0]
        self.assertEqual(p["altitude_ft"], 500)           # 404 - (-96)
        self.assertEqual(p["peak_ft"], 500)               # peak on AGL

    def test_baseline_resets_on_close(self):
        s = LiveState()
        s.update(obs("p", 1, 0, -96, -96, 1))
        s.reset_baseline(1)                               # flight_close resets the pad baseline
        p = view_model(s.snapshot(), {}, {}, {})["panels"][0]
        self.assertIsNone(p["baseline_ft"])               # no baseline -> AGL falls back to raw
        self.assertEqual(p["altitude_ft"], -96)

    def test_no_flight_and_zero_loss(self):
        s = LiveState()
        s.update(obs("t1", 2, 0, -5, 0, 1))
        vm = view_model(s.snapshot(), {(7, 2): {"rx": 3, "gaps": 0}}, open_flights={}, health={})
        p = vm["panels"][0]
        self.assertEqual(p["state"], "pad")
        self.assertEqual(p["seq_loss_pct"], 0.0)
        self.assertIsNone(p["flight_id"])
        self.assertFalse(p["flight_open"])


class TestDensity(unittest.TestCase):
    def test_panel_carries_age_met_and_rssi_trace(self):
        s = LiveState()
        s.update(obs("2026-07-08T00:00:01.000Z", 1, 1, 100, 100, 1, rssi=-52, met=12, call="KC3ZTQ"))
        vm = view_model(s.snapshot(), {}, {1: "2026-07-08-F1"}, {})
        self.assertEqual(vm["callsign"], "KC3ZTQ")                 # operator in the header
        p = vm["panels"][0]
        self.assertEqual(p["received_at"], "2026-07-08T00:00:01.000Z")   # for client-side age
        self.assertEqual(p["met_s"], 12)                          # T+ while a flight is open
        self.assertEqual(p["trace"][0]["rssi"], -52)              # RSSI rides the trace (sparkline)

    def test_events_included(self):
        s = LiveState()
        s.update(obs("t", 1, 0, -5, 0, 1))
        vm = view_model(s.snapshot(), {}, {}, {}, events=[{"type": "event", "event": "flight_open"}])
        self.assertEqual(vm["events"], [{"type": "event", "event": "flight_open"}])


class TestEventsRing(unittest.TestCase):
    def test_captures_events_newest_first_bounded(self):
        ring = EventsRing(maxlen=3)
        for i in range(5):
            ring.capture(f'{{"type":"event","event":"e{i}"}}')
        recent = ring.recent()
        self.assertEqual([e["event"] for e in recent], ["e4", "e3", "e2"])   # newest first, bounded

    def test_ignores_packets_and_garbage(self):
        ring = EventsRing()
        ring.capture('{"type":"packet","src":1}')     # not an event
        ring.capture('not json')                       # garbage
        self.assertEqual(ring.recent(), [])


class TestBaselineV2Live(unittest.TestCase):
    def test_baseline_locks_at_flight_open_and_holds(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"t{i}", 1, 0, -84, -84, i))       # quiet pad
        pad = view_model(s.snapshot(), {}, {}, {})["panels"][0]
        self.assertEqual(pad["baseline_ft"], -84)           # live pad zero pre-flight
        s.update(obs("boost", 1, 1, 500, 500, 18))          # flight opens -> lock
        p = view_model(s.snapshot(), {}, {1: "F1"}, {})["panels"][0]
        self.assertEqual(p["baseline_ft"], -84)             # locked from the pre-boost window
        self.assertEqual(p["altitude_ft"], 584)             # 500 - (-84)
        s.update(obs("asc2", 1, 1, 900, 900, 19))           # climbing
        p = view_model(s.snapshot(), {}, {1: "F1"}, {})["panels"][0]
        self.assertEqual(p["baseline_ft"], -84)             # HELD, not dragged up by flight ALT
        self.assertEqual(p["altitude_ft"], 984)

    def test_reset_unlocks_and_falls_back_to_raw(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"t{i}", 1, 0, -84, -84, i))
        s.update(obs("boost", 1, 1, 900, 900, 18))
        s.reset_baseline(1)                                 # flight_close
        p = view_model(s.snapshot(), {}, {}, {})["panels"][0]
        self.assertIsNone(p["baseline_ft"])                 # unlocked + history cleared
        self.assertEqual(p["altitude_ft"], 900)             # AGL falls back to raw

    def test_unstable_pad_does_not_lock_a_baseline(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"n{i}", 1, 0, -84 if i % 2 else -50, 0, i))   # noisy pad
        s.update(obs("boost", 1, 1, 500, 500, 18))
        p = view_model(s.snapshot(), {}, {1: "F1"}, {})["panels"][0]
        self.assertIsNone(p["baseline_ft"])                 # gate rejects -> no lock
        self.assertEqual(p["altitude_ft"], 500)             # raw during the flight


class TestPeakGatedOnSt(unittest.TestCase):
    """`Max` is only trustworthy once the sled has left the pad — the gate is
    ground.flights.segmenter.max_is_meaningful, imported (never restated) so the
    dashboard, the OLED and the flights index cannot disagree about `Max`."""

    def test_pad_publishes_no_peak_even_though_the_sled_sends_max_zero(self):
        s = LiveState()
        for i in range(18):                                 # quiet pad, raw ALT -84
            s.update(obs(f"t{i}", 1, 0, -84, 0, i))         # firmware sends Max:0 pre-launch
        p = view_model(s.snapshot(), {}, {}, {})["panels"][0]
        self.assertEqual(p["altitude_ft"], 0)               # AGL on the pad is 0 (correct)
        self.assertIsNone(p["peak_ft"])                     # NOT 84 (the negated pad baseline)

    def test_pad_max_zero_never_reaches_the_snapshot(self):
        s = LiveState()
        s.update(obs("t", 1, 0, -84, 0, 1))
        self.assertIsNone(s.snapshot()[1]["peak"])          # gated at the source, not in the view

    def test_peak_publishes_once_st_leaves_the_pad(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"t{i}", 1, 0, -84, 0, i))
        s.update(obs("boost", 1, 1, 500, 500, 18))          # St:1 -> Max is meaningful
        p = view_model(s.snapshot(), {}, {1: "F1"}, {})["panels"][0]
        self.assertEqual(p["peak_ft"], 584)                 # 500 - (-84), on AGL

    def test_peak_gate_is_the_imported_segmenter_predicate(self):
        from ground.dashboard import model
        from ground.flights.segmenter import max_is_meaningful
        self.assertIs(model.max_is_meaningful, max_is_meaningful)   # imported, not restated


class TestFrameWithNoStDoesNotDisturbTheLock(unittest.TestCase):
    """Absence of `St` means 'no information about flight state' — NOT 'not in
    flight'. A Part-97 CALL beacon (required every 10 min) carries no St, and it
    must not unlock the AGL zero mid-flight."""

    def test_call_beacon_midflight_does_not_destroy_the_locked_baseline(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"t{i}", 1, 0, -84, 0, i))         # quiet pad -> baseline -84
        s.update(obs("boost", 1, 1, 500, 500, 18))          # lock at flight_open
        s.update(obs("asc1", 1, 1, 900, 900, 19))
        s.update(beacon("id", 1))                           # Part-97 station ID, no St
        self.assertEqual(s.snapshot()[1]["locked_baseline"], -84)   # lock SURVIVES the beacon
        s.update(obs("asc2", 1, 1, 1200, 1200, 20))
        p = view_model(s.snapshot(), {}, {1: "F1"}, {})["panels"][0]
        self.assertEqual(p["baseline_ft"], -84)
        self.assertEqual(p["altitude_ft"], 1284)            # 1200 - (-84), not the raw 1200

    def test_beacon_frame_itself_reports_the_held_baseline(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"t{i}", 1, 0, -84, 0, i))
        s.update(obs("boost", 1, 1, 500, 500, 18))
        s.update(beacon("id", 1))
        p = view_model(s.snapshot(), {}, {1: "F1"}, {})["panels"][0]
        self.assertEqual(p["baseline_ft"], -84)             # baseline_ft does not blank

    def test_beacon_on_the_pad_does_not_lock_a_baseline(self):
        s = LiveState()
        for i in range(18):
            s.update(obs(f"t{i}", 1, 0, -84, 0, i))
        s.update(beacon("id", 1))                           # no St -> no state change either way
        cur = s.snapshot()[1]
        self.assertIsNone(cur["locked_baseline"])           # absence never LOCKS one either
        self.assertEqual(cur["baseline"], -84)              # the live pad zero is held


if __name__ == "__main__":
    unittest.main()
