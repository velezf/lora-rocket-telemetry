"""Stage-1 publish — the mechanical half of the data hop, pure (2026-08-25).

Given already-fetched session/ops records and the site repo's data directory,
write exactly what projects/lora-flights.qmd reads: the FULL flights.json index
(the page's OJS selector needs every flight, not just the new one) and one
flight's per-packet CSV. Deliberately NOT here: fetching from the Pi (thin scp
glue in the CLI) and committing/pushing the site repo (a HUMAN gate — publish
stops at the diff, per the working agreement).

ONE WRITER PER FORMAT: the index serialization is flights_to_json — the same
bytes `rebuild` writes — pinned by test so publish can never become a second
index writer with its own drift-prone format.
"""
import json
import sys

from ground.flights.derive import derive_flights
from ground.flights.export import flight_rows, rows_to_csv
from ground.flights.flights import flights_to_json


def publish_flight(session_records, ops_records, flight_id, site_dir, silence_s=90):
    """Derive the index from records, write site_dir/flights.json (full index)
    and site_dir/<flight_id>.csv. flight_id=None publishes the LATEST flight's
    CSV. Loud (SystemExit) on an unknown flight_id. Returns the derived flights.
    """
    flights = derive_flights(session_records, ops=ops_records,
                             silence_timeout_s=silence_s)
    if not flights:
        sys.exit("no flights derived from the session — nothing to publish")

    if flight_id is None:
        flight = flights[-1]                      # derive order: chronological
    else:
        flight = next((f for f in flights if f.flight_id == flight_id), None)
        if flight is None:
            sys.exit(f"no flight {flight_id} in the derived index "
                     f"({[f.flight_id for f in flights]})")

    # THE SITE INDEX IS THE ARCHIVE — it accumulates across sessions (first
    # multi-session publish, 2026-08-25: a plain overwrite would have erased
    # July's F1 from the public page). Union semantics: this derivation's
    # flights upsert by flight_id; entries from other sessions are preserved;
    # order by t_start. A fresh dir degenerates to exactly flights_to_json
    # (pinned byte-identical to rebuild's output). A corrupt existing index is
    # LOUD — never silently clobber the archive.
    index_path = site_dir / "flights.json"
    derived = json.loads(flights_to_json(flights))
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text())
        except ValueError:
            sys.exit(f"existing {index_path} is not valid JSON — refusing to "
                     "overwrite the archive; inspect it first")
        ours = {f["flight_id"] for f in derived}
        merged = [f for f in existing if f["flight_id"] not in ours] + derived
        merged.sort(key=lambda f: f["t_start"])
        index_path.write_text(json.dumps(merged))
    else:
        index_path.write_text(flights_to_json(flights))

    rows = flight_rows(session_records, flight)
    (site_dir / f"{flight.flight_id}.csv").write_text(rows_to_csv(rows))
    return flights
