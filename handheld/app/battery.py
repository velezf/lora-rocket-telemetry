"""Battery gauge via pisugar-server (Epic 8.2 slice 6).

The TCP protocol on :8423 answers `get battery` with `battery: <float>` —
or `battery: I2C not connected` when the PiSugar is off the bus (the state
this device lived in until 2026-08-31). Parse is pure; the socket read is
the thin glue main.py hands to battery_tick as a reader callable.
"""
from __future__ import annotations

import socket


def parse_battery(reply: bytes) -> int | None:
    """`battery: 88.47138` -> 88; anything unparsable -> None."""
    try:
        text = reply.decode("ascii", "replace")
        if not text.startswith("battery:"):
            return None
        return int(float(text.split(":", 1)[1].strip()))
    except ValueError:
        return None


def read_battery_pct(host: str = "127.0.0.1", port: int = 8423,
                     timeout: float = 1.0) -> int | None:
    """One `get battery` round-trip. Raises on socket failure — the loop
    counts it (battery_tick); returns None on an unparsable reply."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(b"get battery\n")
        return parse_battery(s.recv(256))
