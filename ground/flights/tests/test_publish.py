"""Host tests for `flights publish` — the Stage-1 data hop, mechanized (2026-08-25).

The hop it replaces: F1's one-off scp + hand-copy into the site repo, which
RESUME warned against becoming habit. The PURE core (publish_flight) takes
already-fetched records and a site directory and writes exactly what the page
reads: the FULL flights.json index (the OJS selector needs every flight, not
just the new one) plus the flight's per-packet CSV. SSH fetching is thin glue
in the CLI and is not tested here; the CLI's --local path drives the same core.
Committing/pushing the site repo stays HUMAN — publish stops at the diff.
"""
import json
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from pathlib import Path

from ground.flights.cli import main
from ground.flights.publish import publish_flight


def _pkt(ts, src, st, alt, seq, extra=None):
    f = {"SYS": 7, "SRC": src, "SEQ": seq, "St": st, "ALT": alt, "Max": alt,
         "G": 1.0, "Pg": 1.0, "T": 20.0, "Batt": 3.9, "MET": 0}
    if extra:
        f.update(extra)
    return {"type": "packet", "received_at": ts, "rssi": -60, "src": src,
            "seq": seq, "fields": f}


def _records():
    return [
        _pkt("2026-07-08T00:00:01.000Z", 1, 1, 100, 1,
             {"Vel": 42.0, "Gmx": 2.1, "Gmn": 0.8, "Wmx": 17.5}),
        _pkt("2026-07-08T00:00:02.000Z", 1, 1, 200, 2),
        # a second, later flight: the index must carry BOTH
        _pkt("2026-07-08T01:00:00.000Z", 1, 1, 300, 10),
        _pkt("2026-07-08T01:00:01.000Z", 1, 1, 400, 11),
    ]


class TestPublishCore(unittest.TestCase):
    def test_writes_full_index_and_flight_csv(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            flights = publish_flight(_records(), [], flight_id=None, site_dir=site,
                                     silence_s=90)
            # flight_id=None -> publish the LATEST flight's CSV
            index = json.loads((site / "flights.json").read_text())
            self.assertEqual(len(index), 2)                    # FULL index, both flights
            latest = index[-1]["flight_id"]
            csv_text = (site / f"{latest}.csv").read_text()
            self.assertTrue(csv_text.startswith("flight_id,received_at,rssi,SYS"))
            self.assertIn(",Vel,", csv_text.splitlines()[0])   # 10 Hz columns present
            self.assertEqual(len(flights), 2)

    def test_explicit_flight_id_selects_that_csv(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            flights = publish_flight(_records(), [], flight_id=None, site_dir=site,
                                     silence_s=90)
            first = flights[0].flight_id
            publish_flight(_records(), [], flight_id=first, site_dir=site, silence_s=90)
            body = (site / f"{first}.csv").read_text()
            self.assertIn("Vel", body.splitlines()[0])
            self.assertIn("42.0", body)                        # the first flight's rows

    def test_unknown_flight_id_is_loud(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                publish_flight(_records(), [], flight_id="nope",
                               site_dir=Path(d), silence_s=90)

    def test_index_matches_rebuild_byte_for_byte(self):
        """Publish must not become a second index writer with its own format:
        flights.json from publish is IDENTICAL to what `rebuild` writes —
        one derivation, one serialization (the one-writer discipline)."""
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"; site.mkdir()
            session = Path(d) / "s.jsonl"
            session.write_text("\n".join(json.dumps(r) for r in _records()))
            index_path = Path(d) / "f.json"
            main(["rebuild", str(session), "--ops", str(Path(d) / "ops.jsonl"),
                  "-o", str(index_path), "--silence", "90"])
            publish_flight(_records(), [], flight_id=None, site_dir=site, silence_s=90)
            self.assertEqual((site / "flights.json").read_text(),
                             index_path.read_text())


class TestPublishCli(unittest.TestCase):
    def test_local_publish_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"; site.mkdir()
            session = Path(d) / "s.jsonl"; ops = Path(d) / "ops.jsonl"
            session.write_text("\n".join(json.dumps(r) for r in _records()))
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["publish", "--local-session", str(session), "--ops", str(ops),
                      "--site", str(site)])
            self.assertTrue((site / "flights.json").exists())
            csvs = list(site.glob("*.csv"))
            self.assertEqual(len(csvs), 1)                     # latest flight only
            out = buf.getvalue()
            self.assertIn("review the site repo diff", out.lower())


if __name__ == "__main__":
    unittest.main()
