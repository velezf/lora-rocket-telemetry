"""Epic 4.3 flights index model (design decisions D1/D2).

Pure, portable Python — stdlib only, no radio/file/I-O. The flight-id scheme,
the Flight record, and round-trippable index (de)serialization. Segmentation
(opening/closing a flight from the packet stream) lives in a separate module;
this one only mints ids and (de)serializes the persisted index.

Flight id (D2): "YYYY-MM-DD-Fn", human-readable and stable. `n` is scoped to
the date, so ids from other dates never affect a day's numbering.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field


@dataclass
class Flight:
    """One flight in the index.

    `stats` holds derived values (peak_alt_ft, duration_s, packets_rx,
    beacons_rx, packets_lost, rssi_min, rssi_max, ...) computed elsewhere —
    this model just carries the dict. `packets_rx` counts TELEMETRY frames only;
    non-telemetry frames are segregated into `beacons_rx` (the definition and
    the policy live in ground/flights/segmenter.py is_telemetry).
    """

    flight_id: str
    src: int
    t_start: str | None
    t_end: str | None
    label: str = ""
    motor: str = ""
    field: str = ""
    stats: dict = dc_field(default_factory=dict)


def next_flight_id(date: str, existing_ids: list[str]) -> str:
    """Return the next "YYYY-MM-DD-Fn" id for `date`.

    n = 1 + (count of existing_ids that start with "<date>-F"). Ids from other
    dates are ignored, so each day numbers its flights independently.
    """
    prefix = date + "-F"
    n = 1 + sum(1 for fid in existing_ids if fid.startswith(prefix))
    return f"{date}-F{n}"


def flights_to_json(flights: list[Flight]) -> str:
    """Serialize a list of Flight records to a JSON array string."""
    return json.dumps([asdict(f) for f in flights])


def flights_from_json(s: str) -> list[Flight]:
    """Deserialize a JSON array string back into Flight records."""
    return [Flight(**obj) for obj in json.loads(s)]
