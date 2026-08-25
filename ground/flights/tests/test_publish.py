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

    def test_published_entries_carry_the_page_schema(self):
        """THE PAGE IS THE CONTRACT (found 2026-08-25, first real publish):
        projects/lora-flights.qmd reads a FLAT, ENRICHED entry — top-level
        stats plus derived date / peak_agl_ft / loss_pct / csv. The F1-era
        one-off publish produced that shape by hand; publish now owns it.
        The derivation stays deterministic from rebuild's Flights — one
        derivation, one (flattened) serialization."""
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            publish_flight(_records(), [], flight_id=None, site_dir=site, silence_s=90)
            index = json.loads((site / "flights.json").read_text())
            e = index[0]
            # every key the page reads, at top level (qmd python + OJS blocks)
            for k in ("flight_id", "date", "src", "t_start", "t_end",
                      "peak_agl_ft", "peak_alt_ft", "baseline_ft", "baseline_n",
                      "duration_s", "packets_rx", "packets_lost", "loss_pct",
                      "rssi_min", "rssi_max", "label", "motor", "field", "csv"):
                self.assertIn(k, e, f"page reads {k} at top level")
            self.assertNotIn("stats", e)                     # flattened, not nested
            self.assertEqual(e["date"], e["t_start"][:10])
            if e["baseline_ft"] is not None:
                self.assertEqual(e["peak_agl_ft"],
                                 e["peak_alt_ft"] - e["baseline_ft"])
            else:
                # this fixture has no locked pad baseline: AGL honestly absent,
                # never fabricated from a missing zero
                self.assertIsNone(e["peak_agl_ft"])
            self.assertEqual(e["csv"], f"lora-flights/{e['flight_id']}.csv")
            rx, lost = e["packets_rx"], e["packets_lost"]
            self.assertEqual(e["loss_pct"], round(lost / (rx + lost) * 100, 2))

    def test_annotations_ride_the_published_entry(self):
        ops = [{"op": "annotate", "src": 1, "at": "2026-07-08T00:00:01.000Z",
                "label": "Maiden", "motor": "F15-6", "field": "Izaak Walton Field"}]
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            publish_flight(_records(), ops, flight_id=None, site_dir=site, silence_s=90)
            e = json.loads((site / "flights.json").read_text())[0]
            self.assertEqual((e["label"], e["motor"], e["field"]),
                             ("Maiden", "F15-6", "Izaak Walton Field"))


class TestPublishAccumulatesTheArchive(unittest.TestCase):
    """The site's flights.json is the ARCHIVE — it accumulates across sessions
    (found at first multi-session publish, 2026-08-25: overwriting with one
    session's derivation would have erased July's F1 from the public page).
    Publish UNIONS: this session's flights upsert by flight_id; existing
    entries from other sessions are preserved; order is by t_start."""

    def test_existing_flights_from_other_sessions_survive(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            # A flight from an EARLIER session/date than anything in _records()
            # (the derived flights are 2026-07-08-*, so this must not collide).
            old = [{"flight_id": "2026-06-01-F1", "date": "2026-06-01", "src": 1,
                    "t_start": "2026-06-01T18:21:57.444Z", "t_end": "2026-06-01T18:23:25.000Z",
                    "peak_alt_ft": -74, "label": "Maiden"}]
            (site / "flights.json").write_text(json.dumps(old))
            publish_flight(_records(), [], flight_id=None, site_dir=site, silence_s=90)
            index = json.loads((site / "flights.json").read_text())
            ids = [f["flight_id"] for f in index]
            self.assertIn("2026-06-01-F1", ids)               # the old flight survives
            self.assertEqual(len(index), 3)                   # 1 old + 2 new
            self.assertEqual(ids, sorted(ids))                # t_start(=id date) order

    def test_republishing_same_session_upserts_not_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            publish_flight(_records(), [], flight_id=None, site_dir=site, silence_s=90)
            publish_flight(_records(), [], flight_id=None, site_dir=site, silence_s=90)
            index = json.loads((site / "flights.json").read_text())
            self.assertEqual(len(index), 2)                   # no duplicate rows

    def test_rederivation_of_this_session_overwrites_its_own_entries(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            flights = publish_flight(_records(), [], flight_id=None, site_dir=site,
                                     silence_s=90)
            fid = flights[0].flight_id
            # simulate a stale earlier publish of the SAME flight with old stats
            index = json.loads((site / "flights.json").read_text())
            for f in index:
                if f["flight_id"] == fid: f["packets_lost"] = 999999
            (site / "flights.json").write_text(json.dumps(index))
            publish_flight(_records(), [], flight_id=None, site_dir=site, silence_s=90)
            index = json.loads((site / "flights.json").read_text())
            row = next(f for f in index if f["flight_id"] == fid)
            self.assertNotEqual(row.get("packets_lost"), 999999)   # fresh derivation wins


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
