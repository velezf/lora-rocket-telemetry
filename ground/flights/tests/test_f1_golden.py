# pyright: reportAttributeAccessIssue=false
# ^ the fixture is all-valid frames, so decode() returns DecodeOk; pyright doesn't
#   narrow the DecodeOk|DecodeError union across the equality assert below.
"""Real-RF golden regression — the first real flight, 2026-07-08-F1 (shake test).

A version-controlled slice of the actual session log (75 packets + the
flight_open/flight_close events) plus the ops-journal annotation, captured live
on apogee-gs. The full contract chain — decode(raw bytes) -> segment -> derive —
must reproduce F1's index entry EXACTLY. Real over-the-air bytes guard every
future change to the decoder, the segmenter, and the derivation against silent
regressions that a hand-written fixture might not exercise (real SEQ gap, real
RSSI spread, real St 1->2 transition, negative pad-relative altitudes).
"""
import json
import unittest
from pathlib import Path

from ground.decode.v1 import decode
from ground.flights.derive import derive_flights

_FIX = Path(__file__).parent / "fixtures"


def _read_jsonl(name):
    return [json.loads(ln) for ln in (_FIX / name).read_text().splitlines() if ln.strip()]


class TestF1Golden(unittest.TestCase):
    def setUp(self):
        self.records = _read_jsonl("f1_session.jsonl")
        self.ops = _read_jsonl("f1_ops.jsonl")
        self.packets = [r for r in self.records if r.get("type") == "packet"]

    def test_decode_reproduces_every_real_packet(self):
        """Each recorded raw ASCII frame re-decodes to exactly the stored fields —
        the decoder against real over-the-air bytes, not a synthesized vector."""
        self.assertEqual(len(self.packets), 75)
        for r in self.packets:
            self.assertEqual(decode(r["raw"].encode()).fields, r["fields"], r["raw"])

    def test_derive_reproduces_f1_index_entry_exactly(self):
        """decode -> segment -> derive over the real slice reproduces F1's index
        entry and its annotation, byte-for-byte on the numbers."""
        flights = derive_flights(self.records, ops=self.ops, silence_timeout_s=90)
        self.assertEqual(len(flights), 1)
        f = flights[0]
        self.assertEqual(f.flight_id, "2026-07-08-F1")
        self.assertEqual(f.src, 1)
        self.assertEqual(f.t_start, "2026-07-08T18:21:57.444Z")
        self.assertEqual(f.t_end, "2026-07-08T18:23:25.000Z")
        self.assertEqual(f.label, "shake test")          # annotation survives derivation
        self.assertEqual(f.stats, {
            "peak_alt_ft": -74, "duration_s": 87.556,
            "packets_rx": 75, "packets_lost": 1,          # one real SEQ gap during the swing
            "rssi_min": -38, "rssi_max": -14,
        })

    def test_derivation_is_deterministic(self):
        """Re-derivation yields an identical index (the round-trip proved live)."""
        a = derive_flights(self.records, ops=self.ops, silence_timeout_s=90)[0]
        b = derive_flights(self.records, ops=self.ops, silence_timeout_s=90)[0]
        self.assertEqual((a.flight_id, a.t_start, a.t_end, a.label, a.stats),
                         (b.flight_id, b.t_start, b.t_end, b.label, b.stats))


if __name__ == "__main__":
    unittest.main()
