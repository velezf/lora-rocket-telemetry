"""Stage-1 publish DATA generation (pure, stdlib only).

`flights publish` ships DATA ONLY into the portfolio site repo: a `flights.json`
summary (consumed client-side by the Stage-2 archive page's OJS) plus a per-flight
CSV (the packet trace, via ground.flights.export). It NEVER writes .qmd — the
archive page is a hand-polished Stage-2 artifact authored once in the site repo.

Permalinks are OJS URL-param deep links into that single archive page — no generated
stub pages. The URL scheme lives here, once.
"""

# The archive is a flat project page (projects/<slug>.qmd convention, appears in the
# grid) at /projects/lora-flights.html; a flight is deep-linked with ?flight=<id>,
# read client-side by the page's OJS. Its data lives in a colocated projects/lora-flights/.
_ARCHIVE_URL = "https://velezf.github.io/projects/lora-flights.html"
_DATA_DIR = "lora-flights"          # relative to the page (projects/lora-flights.qmd)


def permalink(flight_id: str) -> str:
    return f"{_ARCHIVE_URL}?flight={flight_id}"


def _summary(f):
    s = f.stats
    base = s.get("baseline_ft")
    peak_raw = s.get("peak_alt_ft")
    # peak AGL only when a baseline locked; else null (never silently pass raw as AGL)
    peak_agl = (peak_raw - base) if (base is not None and peak_raw is not None) else None
    rx, lost = s.get("packets_rx", 0), s.get("packets_lost", 0)
    return {
        "flight_id": f.flight_id,
        "date": (f.t_start or "")[:10],
        "src": f.src,
        "t_start": f.t_start,
        "t_end": f.t_end,
        "peak_agl_ft": peak_agl,
        "peak_alt_ft": peak_raw,
        "baseline_ft": base,
        "baseline_n": s.get("baseline_n"),
        "duration_s": s.get("duration_s"),
        "packets_rx": rx,
        "packets_lost": lost,
        "loss_pct": round(100.0 * lost / (rx + lost), 2) if (rx + lost) else 0.0,
        "rssi_min": s.get("rssi_min"),
        "rssi_max": s.get("rssi_max"),
        "label": f.label,
        "motor": f.motor,
        "field": f.field,
        "csv": f"{_DATA_DIR}/{f.flight_id}.csv",   # relative to the archive page
    }


def flights_summary(flights):
    """The flights.json payload: one summary record per flight, newest first."""
    return sorted((_summary(f) for f in flights),
                  key=lambda r: r["date"], reverse=True)


def write_flight_data(site_dir, all_flights, flight_id, session_records):
    """Stage-1 ship: DATA ONLY into the site repo under projects/<_DATA_DIR>/ — the
    full flights.json (upserted) plus this flight's CSV trace. Writes no .qmd. Returns
    the flight's permalink."""
    import json
    from pathlib import Path
    from ground.flights.export import flight_rows, rows_to_csv

    out = Path(site_dir) / "projects" / _DATA_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "flights.json").write_text(json.dumps(flights_summary(all_flights), indent=2))
    flight = next(f for f in all_flights if f.flight_id == flight_id)
    (out / f"{flight_id}.csv").write_text(rows_to_csv(flight_rows(session_records, flight)))
    return permalink(flight_id)
