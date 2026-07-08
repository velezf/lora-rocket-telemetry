"""Flight segmentation — derives flights as metadata over the packet stream.

Pure and deterministic: the caller passes each accepted packet's ISO timestamp
(for the record) and a monotonic clock `t` in seconds (for silence/duration
arithmetic), so open/close decisions are host-testable with no wall clock.

Policy (D2 + multi-bird + journal amendment):
- OPEN when a SRC's packet reports St == ascent and that SRC has no open flight;
  or a manual `force_open`.
- CONCURRENT: flights are tracked per SRC — multiple birds open at once.
- CLOSE on silence, or a manual close. A manual close/open beats the silence
  timeout: pass the SRC in `protect` to check_timeouts so silence can't preempt a
  pending manual close.
Flight IDs come from ground.flights.flights.next_flight_id (stable YYYY-MM-DD-Fn),
assigned at open and never reused.
"""
from ground.flights.flights import Flight, next_flight_id

ST_ASCENT = 1  # ADR 0001 St codes: 0 pad / 1 ascent / 2 descent


class FlightSegmenter:
    def __init__(self, silence_timeout_s: float = 90):
        self.silence_timeout_s = silence_timeout_s
        self._open = {}        # src -> working flight state
        self._ids = []         # every flight id ever assigned (next_flight_id + no reuse)

    def open_srcs(self):
        return list(self._open.keys())

    def open_flight_ids(self):
        return {src: fl["flight_id"] for src, fl in self._open.items()}

    def _start(self, received_at, t, src, alt, rssi, seq, packets):
        fid = next_flight_id(received_at[:10], self._ids)
        self._ids.append(fid)
        self._open[src] = {
            "flight_id": fid, "src": src,
            "t_start_iso": received_at, "t_start": t,
            "t_end_iso": received_at, "t_end": t,
            "peak_alt": alt, "packets": packets,
            "rssi_min": rssi, "rssi_max": rssi,
            "last_seq": seq, "gaps": 0,
        }
        return fid

    def force_open(self, received_at, t, src):
        """Manual open (missed the boost packet). No-op if already open."""
        if src not in self._open:
            self._start(received_at, t, src, alt=0, rssi=None, seq=None, packets=0)

    def observe(self, received_at, t, src, st, alt, rssi, seq):
        """Feed one accepted packet (foreign/unknown-SRC already filtered upstream)."""
        fl = self._open.get(src)
        if fl is None:
            if st == ST_ASCENT:
                return self._start(received_at, t, src, alt, rssi, seq, packets=1)  # -> new flight_id
            return None  # pad packets (or descent w/o prior ascent) don't open a flight
        fl["t_end_iso"] = received_at
        fl["t_end"] = t
        fl["packets"] += 1
        fl["peak_alt"] = max(fl["peak_alt"], alt)
        fl["rssi_min"] = rssi if fl["rssi_min"] is None else min(fl["rssi_min"], rssi)
        fl["rssi_max"] = rssi if fl["rssi_max"] is None else max(fl["rssi_max"], rssi)
        if fl["last_seq"] is None:
            fl["last_seq"] = seq
        else:
            fl["gaps"] += (seq - fl["last_seq"] - 1) % 65536   # uint16 wraparound-aware
            fl["last_seq"] = seq

    def check_timeouts(self, t, protect=frozenset()):
        """Close flights silent longer than the timeout, except SRCs in `protect`
        (which have a pending manual close). Returns the closed Flights."""
        closed = []
        for src, fl in list(self._open.items()):
            if src not in protect and t - fl["t_end"] > self.silence_timeout_s:
                closed.append(self._finalize(self._open.pop(src)))
        return closed

    def close(self, src):
        """Manually close a SRC's open flight. Returns the Flight, or None."""
        fl = self._open.pop(src, None)
        return self._finalize(fl) if fl else None

    def _finalize(self, fl) -> Flight:
        return Flight(
            flight_id=fl["flight_id"], src=fl["src"],
            t_start=fl["t_start_iso"], t_end=fl["t_end_iso"],
            stats={
                "peak_alt_ft": fl["peak_alt"],
                "duration_s": round(fl["t_end"] - fl["t_start"], 3),
                "packets_rx": fl["packets"],
                "packets_lost": fl["gaps"],
                "rssi_min": fl["rssi_min"],
                "rssi_max": fl["rssi_max"],
            },
        )
