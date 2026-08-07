# pyright: reportAttributeAccessIssue=false
# ^ fixture frames are all valid, so decode() returns DecodedPacket; pyright does
#   not narrow the union across the runtime asserts (same rationale as test_f1_golden).
"""E2E gate for the two new frame SHAPES (2026-08-08 E+F decision) — the same
decode -> segment -> derive chain the F1 golden guards, over fixtures that carry
the ten new tags.

Fixtures (ground/flights/tests/fixtures/):
- newtags_worst_frames.jsonl — one worst-FORM FLIGHT frame and one worst-form
  PAD frame, every value at its longest legal rendering under the recorded range
  assumptions (see ground/decode/tests/test_newtags.py for the table).
- newtags_transition_session.jsonl — 18 quiet pad packets (1 Hz) then a 10 Hz
  flight in which a St:0-SHAPED frame (pad content: raw 9-DoF, Max:0) arrives
  BETWEEN St:1 frames with SEQ continuous — the state-transition case. It must
  ride the ADDITIVE rules (present fields decode, absent stay absent), not a
  special case, and flight accounting must not break.

BYTE-LENGTH NOTE, measured not assumed: the worst-form payloads are 151 B
(FLIGHT) and 209 B (PAD) on the wire. The session decision quotes 152 B / 210 B
— exactly one more each, i.e. C-string buffer occupancy (payload + NUL). Both
sit far under RH_RF95_MAX_MESSAGE_LEN (251). The asserts pin the measured
payload lengths so a fixture edit that grows a frame past the decision's
envelope fails loudly.
"""
import json
import unittest
from pathlib import Path

from ground.decode.v1 import decode
from ground.flights.derive import derive_flights

_FIX = Path(__file__).parent / "fixtures"


def _read_jsonl(name):
    return [json.loads(ln) for ln in (_FIX / name).read_text().splitlines() if ln.strip()]


class TestWorstFormFrames(unittest.TestCase):
    def setUp(self):
        self.frames = {r["shape"]: r for r in _read_jsonl("newtags_worst_frames.jsonl")}

    def test_flight_shape_worst_form_decodes_exactly(self):
        r = self.frames["flight"]
        self.assertEqual(len(r["raw"]), 151)          # +1 NUL = the decision's 152
        d = decode(r["raw"].encode())
        self.assertTrue(d.ok)
        self.assertEqual(d.fields, r["fields"])       # stored fields re-derivable
        self.assertEqual(d.unknown, {})               # every tag known
        # spot-pin the values, not just round-trip equality
        self.assertEqual(d.fields["SEQ"], 65535)
        self.assertEqual(d.fields["ALT"], -19999)
        self.assertEqual(d.fields["Max"], 199999)
        self.assertAlmostEqual(d.fields["Vel"], -1999.9)
        self.assertAlmostEqual(d.fields["Gmx"], 199.9)
        self.assertAlmostEqual(d.fields["Gmn"], 199.9)
        self.assertAlmostEqual(d.fields["Wmx"], 2293.8)
        self.assertNotIn("Gyx", d.fields)             # FLIGHT shape has no raw 9-DoF

    def test_pad_shape_worst_form_decodes_exactly(self):
        r = self.frames["pad"]
        self.assertEqual(len(r["raw"]), 209)          # +1 NUL = the decision's 210
        d = decode(r["raw"].encode())
        self.assertTrue(d.ok)
        self.assertEqual(d.fields, r["fields"])
        self.assertEqual(d.unknown, {})
        for tag in ("Gyx", "Gyy", "Gyz"):
            self.assertAlmostEqual(d.fields[tag], -2293.8)
        for tag in ("Mgx", "Mgy", "Mgz"):
            self.assertAlmostEqual(d.fields[tag], -478.9)
        self.assertAlmostEqual(d.fields["Vel"], -1999.9)
        self.assertNotIn("Wmx", d.fields)             # PAD shape carries no Wmx


class TestPadFrameMidFlight(unittest.TestCase):
    """The transition sequence: St:1, St:1, St:1, [St:0 pad-shaped], St:1 ...
    with SEQ continuous. Additive rules only — no special case anywhere."""

    def setUp(self):
        self.records = _read_jsonl("newtags_transition_session.jsonl")

    def test_every_frame_redecodes_to_stored_fields(self):
        self.assertEqual(len(self.records), 28)       # 18 pad + 10 flight-span
        for r in self.records:
            d = decode(r["raw"].encode())
            self.assertTrue(d.ok, r["raw"])
            self.assertEqual(d.fields, r["fields"], r["raw"])
            self.assertEqual(d.unknown, {}, r["raw"])

    def test_transition_frame_is_pad_shaped_and_mid_flight(self):
        """Guard the fixture's own premise so it cannot rot: SEQ 21 carries
        St:0 + raw 9-DoF + Max:0, and its neighbors are St:1."""
        by_seq = {r["fields"]["SEQ"]: r["fields"] for r in self.records}
        self.assertEqual(by_seq[20]["St"], 1)
        self.assertEqual(by_seq[21]["St"], 0)         # the artifact
        self.assertEqual(by_seq[22]["St"], 1)
        self.assertEqual(by_seq[21]["Max"], 0)        # pad-shape Max — the trap
        self.assertEqual(by_seq[21]["ALT"], 470)      # real mid-climb altitude
        self.assertAlmostEqual(by_seq[21]["Gyx"], -0.4)
        self.assertNotIn("Wmx", by_seq[21])           # pad shape
        self.assertNotIn("Gyx", by_seq[20])           # flight shape

    def test_flight_accounting_survives_the_transition_frame(self):
        flights = derive_flights(self.records, silence_timeout_s=90)
        self.assertEqual(len(flights), 1)             # did NOT split the flight
        f = flights[0]
        self.assertEqual(f.src, 1)
        self.assertEqual(f.t_start, "2026-08-08T17:00:18.000Z")
        self.assertEqual(f.t_end, "2026-08-08T17:00:18.900Z")
        self.assertEqual(f.stats, {
            # 10 telemetry frames from open (SEQ 18) through descent (SEQ 27),
            # INCLUDING the St:0-shaped SEQ 21 — it carries St, so it is
            # telemetry (segmenter.is_telemetry), never a beacon.
            "packets_rx": 10,
            "beacons_rx": 0,
            # SEQ 18..27 continuous across the transition frame: zero loss.
            "packets_lost": 0,
            # Peak comes from Max on the St:1/St:2 frames (905). The transition
            # frame's Max:0 is gated out by max_is_meaningful(St:0); its Gmx and
            # the 9-DoF magnitudes never enter altitude accounting.
            "peak_alt_ft": 905,
            "duration_s": 0.9,
            "rssi_min": -50, "rssi_max": -38,
            # AGL zero locked from the quiet 1 Hz pad window before the boost.
            "baseline_ft": -84, "baseline_n": 15,
        })


if __name__ == "__main__":
    unittest.main()
