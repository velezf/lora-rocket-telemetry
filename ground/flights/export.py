"""Per-flight export — materialize pandas-friendly rows from the raw session log
plus a flight's segment metadata. One row per accepted packet in the flight's
(SRC + time span), consistent columns/dtypes; CSV or JSON. Raw data never moves —
this is a derived view (D2).
"""
import csv
import io
import json

from ground.flights.segmenter import is_telemetry

# ADR-0001 field tags carried as one column each, plus the log/flight context.
_FIELD_TAGS = ["SYS", "SRC", "SEQ", "St", "ALT", "Max", "G", "Pg", "T", "Batt", "MET"]
COLUMNS = ["flight_id", "received_at", "rssi"] + _FIELD_TAGS


def flight_rows(records, flight):
    """Rows for `flight` from `records` (the session JSONL, parsed): TELEMETRY
    packet records whose SRC matches and whose received_at falls within
    [t_start, t_end].

    Non-telemetry frames are excluded on the same rule the index uses
    (`is_telemetry`), so the trace and the flight's `packets_rx` agree: a bare
    `CALL` beacon would otherwise export as a row of nulls in the very CSV whose
    summary excludes it.
    """
    rows = []
    for r in records:
        if r.get("type") != "packet" or r.get("src") != flight.src:
            continue
        ts = r.get("received_at")
        if ts is None or ts < flight.t_start or ts > flight.t_end:
            continue
        fields = r.get("fields", {})
        if not is_telemetry(fields.get("St")):
            continue
        row = {"flight_id": flight.flight_id, "received_at": ts, "rssi": r.get("rssi")}
        for tag in _FIELD_TAGS:
            row[tag] = fields.get(tag)
        rows.append(row)
    return rows


def rows_to_csv(rows) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def rows_to_json(rows) -> str:
    return json.dumps(rows)
