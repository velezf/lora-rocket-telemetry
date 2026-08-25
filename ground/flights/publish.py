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

    (site_dir / "flights.json").write_text(flights_to_json(flights))
    rows = flight_rows(session_records, flight)
    (site_dir / f"{flight.flight_id}.csv").write_text(rows_to_csv(rows))
    return flights
