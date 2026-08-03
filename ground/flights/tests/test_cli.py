"""Host tests for the flights CLI — the journal workflow (three files, one writer)."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ground.flights.cli import main
from ground.flights.flights import flights_from_json


def _pktline(ts, src, st, alt, seq):
    return json.dumps({"type": "packet", "received_at": ts, "rssi": -60, "src": src, "seq": seq,
                       "fields": {"SYS": 7, "SRC": src, "SEQ": seq, "St": st, "ALT": alt, "Max": alt}})


def _beaconline(ts, src):
    """A standalone Part-97 `CALL` beacon: no `St`, no `ALT`, no `SEQ`."""
    return json.dumps({"type": "packet", "received_at": ts, "rssi": -60, "src": src, "seq": None,
                       "fields": {"SYS": 7, "SRC": src}, "unknown": {"CALL": "KC3ZTQ"}})


class TestOpsJournalWorkflow(unittest.TestCase):
    def _paths(self, d):
        d = Path(d)
        return d / "s.jsonl", d / "ops.jsonl", d / "f.json"

    def test_annotate_journaled_and_survives_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            session, ops, index = self._paths(d)
            session.write_text("\n".join([
                _pktline("2026-07-08T00:00:01.000Z", 1, 1, 100, 1),
                _pktline("2026-07-08T00:00:02.000Z", 1, 2, 80, 2)]))
            main(["rebuild", str(session), "--ops", str(ops), "-o", str(index), "--silence", "30"])
            fid = flights_from_json(index.read_text())[0].flight_id
            main(["annotate", fid, "--index", str(index), "--ops", str(ops), "--label", "Maiden", "--motor", "F15"])
            self.assertIn("annotate", ops.read_text())            # journaled, not written to index
            main(["rebuild", str(session), "--ops", str(ops), "-o", str(index), "--silence", "30"])
            f = flights_from_json(index.read_text())[0]
            self.assertEqual((f.label, f.motor), ("Maiden", "F15"))  # survived re-derivation

    def test_manual_close_journaled_beats_silence(self):
        with tempfile.TemporaryDirectory() as d:
            session, ops, index = self._paths(d)
            session.write_text("\n".join([
                _pktline("2026-07-08T00:00:00.000Z", 1, 1, 100, 1),
                _pktline("2026-07-08T00:03:20.000Z", 1, 1, 200, 2)]))   # would auto-split
            main(["rebuild", str(session), "--ops", str(ops), "-o", str(index), "--silence", "90"])
            self.assertEqual(len(flights_from_json(index.read_text())), 2)
            fid = flights_from_json(index.read_text())[0].flight_id
            main(["close", fid, "--index", str(index), "--ops", str(ops), "--at", "2026-07-08T00:05:00.000Z"])
            main(["rebuild", str(session), "--ops", str(ops), "-o", str(index), "--silence", "90"])
            self.assertEqual(len(flights_from_json(index.read_text())), 1)  # manual close beat silence

    def test_export_after_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            session, ops, index = self._paths(d)
            out = Path(d) / "e.csv"
            session.write_text("\n".join([
                _pktline("2026-07-08T00:00:01.000Z", 1, 1, 100, 1),
                _pktline("2026-07-08T00:00:02.000Z", 1, 2, 80, 2)]))
            main(["rebuild", str(session), "--ops", str(ops), "-o", str(index), "--silence", "30"])
            fid = flights_from_json(index.read_text())[0].flight_id
            main(["export", str(index), str(session), fid, "--format", "csv", "-o", str(out)])
            lines = out.read_text().splitlines()
            self.assertIn("flight_id", lines[0])
            self.assertEqual(len(lines), 1 + 2)   # header + 2 packets

    def test_list_surfaces_beacons_alongside_packets(self):
        """`beacons_rx` is VISIBLE, not discarded. Beacons are kept out of
        `packets_rx` (see ground/flights/segmenter.py is_telemetry), so without a
        column of their own an operator has no way to tell a station that
        identified itself from one that transmitted nothing at all."""
        with tempfile.TemporaryDirectory() as d:
            session, ops, index = self._paths(d)
            session.write_text("\n".join([
                _pktline("2026-07-08T00:00:01.000Z", 1, 1, 100, 1),
                _beaconline("2026-07-08T00:00:02.000Z", 1),
                _pktline("2026-07-08T00:00:03.000Z", 1, 2, 80, 2)]))
            main(["rebuild", str(session), "--ops", str(ops), "-o", str(index), "--silence", "30"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["list", str(index)])
            self.assertIn("rx=2", buf.getvalue())          # telemetry only
            self.assertIn("beacons=1", buf.getvalue())     # segregated, but shown


if __name__ == "__main__":
    unittest.main()
