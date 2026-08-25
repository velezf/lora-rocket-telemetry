"""Stage-1 publish — the mechanical half of the data hop, pure (2026-08-25).

Given already-fetched session/ops records and the site repo's data directory,
write exactly what projects/lora-flights.qmd reads: the FULL flights.json index
(the page's OJS selector needs every flight, not just the new one) and one
flight's per-packet CSV. Deliberately NOT here: fetching from the Pi (thin scp
glue in the CLI) and committing/pushing the site repo (a HUMAN gate — publish
stops at the diff, per the working agreement).

THE PAGE IS THE CONTRACT: projects/lora-flights.qmd reads FLAT, ENRICHED
entries (top-level stats plus derived date / peak_agl_ft / loss_pct / csv —
the shape the F1-era one-off publish produced by hand). publish owns that
flattening now, derived deterministically from rebuild's Flights and pinned
by test — one derivation, one (flattened) serialization.
"""
import json
import sys

from dataclasses import asdict

from ground.flights.derive import derive_flights
from ground.flights.export import flight_rows, rows_to_csv


def _site_entry(flight):
    """One page-schema entry: Flight flattened + the page's derived fields."""
    f = asdict(flight)
    s = f.pop("stats") or {}
    peak, base = s.get("peak_alt_ft"), s.get("baseline_ft")
    rx, lost = s.get("packets_rx") or 0, s.get("packets_lost") or 0
    return {
        "flight_id": f["flight_id"],
        "date": f["t_start"][:10],
        "src": f["src"],
        "t_start": f["t_start"],
        "t_end": f["t_end"],
        "peak_agl_ft": (peak - base) if peak is not None and base is not None else None,
        "peak_alt_ft": peak,
        "baseline_ft": base,
        "baseline_n": s.get("baseline_n"),
        "duration_s": s.get("duration_s"),
        "packets_rx": rx,
        "packets_lost": lost,
        "loss_pct": round(lost / (rx + lost) * 100, 2) if (rx + lost) else 0.0,
        "rssi_min": s.get("rssi_min"),
        "rssi_max": s.get("rssi_max"),
        "label": f.get("label"),
        "motor": f.get("motor"),
        "field": f.get("field"),
        "csv": f"lora-flights/{f['flight_id']}.csv",
    }


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
    # order by t_start. A corrupt existing index is LOUD — never silently
    # clobber the archive. Entries are page-schema (_site_entry), so an
    # earlier nested-schema publish of the same flight is repaired by upsert.
    index_path = site_dir / "flights.json"
    derived = [_site_entry(f) for f in flights]
    merged = derived
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

    rows = flight_rows(session_records, flight)
    (site_dir / f"{flight.flight_id}.csv").write_text(rows_to_csv(rows))
    return flights
