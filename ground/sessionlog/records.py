"""Epic 4.2 session-log record builders (design decisions D1 + D1/D2 addendum).

The ingest service appends one JSON Lines record per decoded packet, plus
advisory EVENT records. These builders are PURE and deterministic: timestamps
are supplied by the caller (no time/datetime/clock reads here), and nothing is
written to disk — callers own serialization and I/O.

Records are append-only. `raw` is stored VERBATIM so a session log can be
re-decoded later if the decoder improves.
"""
from __future__ import annotations

import json

from ground.decode.v1 import DecodedPacket


def packet_record(received_at: str, rssi, decoded: DecodedPacket) -> dict:
    """Build a `type="packet"` record from a decoded v1 packet.

    `received_at` is an ISO-8601 millisecond string supplied by the caller.
    `sys`/`src`/`seq` are lifted out of the decoded fields for convenience
    (None when absent); the full typed `fields`, tolerated `unknown` tags, and
    the verbatim `raw` payload are all carried through.
    """
    fields = decoded.fields
    return {
        "type": "packet",
        "received_at": received_at,
        "rssi": rssi,
        "sys": fields.get("SYS"),
        "src": fields.get("SRC"),
        "seq": fields.get("SEQ"),
        "fields": fields,
        "unknown": decoded.unknown,
        "raw": decoded.raw,
    }


def event_record(received_at: str, event: str, **detail) -> dict:
    """Build a `type="event"` advisory record.

    `event` is one of the usage-contract events
    ("flight_open", "flight_close", "annotation", "service_start",
    "service_stop"); any extra `detail` kwargs are merged into the record.
    Advisory records are never rewritten — a usage contract, not enforced here.
    """
    return {
        "type": "event",
        "received_at": received_at,
        "event": event,
        **detail,
    }


def to_jsonl(record: dict) -> str:
    """Serialize a record as one compact JSON Lines row (trailing newline)."""
    return json.dumps(record, separators=(",", ":")) + "\n"
