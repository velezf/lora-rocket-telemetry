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

ABSENT IS NOT ZERO. `alt`, `seq` and `max_alt` are all optional: a frame that
omits one is still a received packet, but contributes nothing to the stat it
cannot supply. 0 is a legal value for every one of them, so a caller must never
coalesce None to 0 on the way in — that fabricated a 65535-packet loss (the
uint16 gap arithmetic wraps) and a 0 ft peak.

NOT EVERY FRAME IS TELEMETRY. A frame with no `St` is a bare Part-97 `CALL`
beacon; it is counted in `beacons_rx` and takes no other part in the flight.
`is_telemetry` below is the single definition and carries the rationale.
"""
from ground.flights.flights import Flight, next_flight_id
from ground.flights.baseline import pad_baseline, trim_history

ST_PAD = 0     # ADR 0001 St codes: 0 pad / 1 ascent / 2 descent
ST_ASCENT = 1


def _extend(cur, val, fn):
    """Fold `val` into a running min/max that may not have started yet."""
    if val is None:
        return cur
    return val if cur is None else fn(cur, val)


def max_is_meaningful(st) -> bool:
    """Is a frame's `Max` tag trustworthy, given the frame's `St`?

    THE SINGLE DEFINITION — every consumer of `Max` must call this rather than
    restate the check. Two copies of this rule in two modules is how a third,
    disagreeing copy gets written.

    WHY the gate exists: `Max` is the sled's OWN running maximum altitude, which
    makes it strictly better than max(received ALT) — the ground loses the true
    peak to a single dropped packet near apogee, silently, whereas any ONE
    post-apogee frame carries the sled's answer. But the firmware transmits
    `Max:0` before launch, and **0 ft is a legal altitude, not a sentinel**. The
    v1 wire format has no way to say ABSENT distinctly from ZERO (ADR 0001), so
    the reader has to infer it. F1 flew ENTIRELY below 0 ft raw (pad baseline
    -84 ft), so an ungated max(Max) over that real flight yields 0 — a published
    **+84 ft AGL for a flight that actually reached 10 ft**, a bigger wrong
    number than the dropped-packet bug it was meant to fix.

    So `Max` counts only once `St` says the sled has left the pad. An absent
    `St` (a bare `CALL` beacon carries none) is not trusted either: nothing in
    such a frame establishes that launch has happened.

    Known consumers: `_peak_candidates` below (the flights index) and the
    dashboard/OLED view model, which publishes `peak_ft` from the same tag.
    """
    return st is not None and st != ST_PAD


def is_telemetry(st) -> bool:
    """May this frame participate in flight accounting?

    THE SINGLE DEFINITION — the one place that decides what is telemetry. The
    discriminator is the ABSENCE OF `St`, never the presence of `CALL`: a `CALL`
    riding on a complete telemetry frame is telemetry, and a bare beacon carries
    no `St` at all.

    POLICY: frames that are not telemetry do not participate in flight
    accounting. This is the foreign-traffic rule of `ground/ingest/core.py:12`
    applied to a second class of non-telemetry frame — counted and segregated,
    never merged. A Part-97 `CALL` beacon is the station identifying itself: it
    is evidence the RADIO is alive, not evidence about the flight.

    Two consequences, both implemented in `observe` below:
    - a beacon is counted in `beacons_rx`, never in `packets_rx`. It carries no
      `SEQ`, so it cannot participate in loss accounting; in the denominator
      while absent from the sequence space it would make the published loss
      percentage read artificially LOW.
    - a beacon does not extend `t_end` and so does not hold off the silence
      timeout. The 90 s rule detects "the vehicle stopped sending telemetry"; if
      beacons held a flight open, a landed rocket beaconing every 60 s would run
      until the battery died and `duration_s` would become the interval between
      ID transmissions. The flight must not be defined by its callsign.
    """
    return st is not None


def _peak_candidates(st, alt, max_alt):
    """Altitudes from one frame that may raise a flight's peak."""
    vals = [] if alt is None else [alt]
    if max_alt is not None and max_is_meaningful(st):
        vals.append(max_alt)
    return vals


class FlightSegmenter:
    def __init__(self, silence_timeout_s: float = 90):
        self.silence_timeout_s = silence_timeout_s
        self._open = {}        # src -> working flight state
        self._ids = []         # every flight id ever assigned (next_flight_id + no reuse)
        self._alt_hist = {}    # src -> recent (t, ALT) (pre-boost window feeds the AGL baseline)

    def open_srcs(self):
        return list(self._open.keys())

    def open_flight_ids(self):
        return {src: fl["flight_id"] for src, fl in self._open.items()}

    def _push_alt(self, src, t, alt):
        if alt is None:
            return                  # a frame with no ALT is not a pad sample
        buf = self._alt_hist.setdefault(src, [])
        buf.append((t, alt))
        buf[:] = trim_history(buf)  # keep only the trailing time window (any rate)

    def _start(self, received_at, t, src, peak, rssi, seq, packets):
        fid = next_flight_id(received_at[:10], self._ids)
        self._ids.append(fid)
        # Baseline locked retrospectively from the pre-boost window (the opening packet
        # is pushed to history only afterward, so it never enters its own baseline).
        base_ft, base_n = pad_baseline(self._alt_hist.get(src, []))
        self._open[src] = {
            "flight_id": fid, "src": src,
            "t_start_iso": received_at, "t_start": t,
            "t_end_iso": received_at, "t_end": t,
            "peak_alt": peak, "packets": packets, "beacons": 0,
            "rssi_min": rssi, "rssi_max": rssi,
            "last_seq": seq, "gaps": 0,
            "baseline_ft": base_ft, "baseline_n": base_n,
        }
        return fid

    def force_open(self, received_at, t, src):
        """Manual open (missed the boost packet). No-op if already open."""
        if src not in self._open:
            self._start(received_at, t, src, peak=None, rssi=None, seq=None, packets=0)

    def observe(self, received_at, t, src, st, alt, rssi, seq, max_alt=None):
        """Feed one accepted packet (foreign/unknown-SRC already filtered upstream).

        `alt`, `seq` and `max_alt` may be None — the frame simply didn't carry
        them. Absent fields are skipped, never read as 0 (see the module docstring).

        An absent `st` means the frame is NOT TELEMETRY (a bare `CALL` beacon):
        it is counted in `beacons_rx` and touches nothing else — see
        `is_telemetry` for the policy and why. This is the only segregation
        point, so the live path and the offline rebuild cannot disagree.
        """
        fl = self._open.get(src)
        if not is_telemetry(st):
            if fl is not None:
                fl["beacons"] += 1     # visible, but out of the flight's accounting
            return None                # no t_end, no packets_rx, no rssi, no open

        peak_in = _peak_candidates(st, alt, max_alt)
        if fl is None:
            if st == ST_ASCENT:
                peak = max(peak_in) if peak_in else None
                fid = self._start(received_at, t, src, peak, rssi, seq, packets=1)  # -> new flight_id
                self._push_alt(src, t, alt)
                return fid
            self._push_alt(src, t, alt)   # pad packet -> baseline history
            return None  # pad packets (or descent w/o prior ascent) don't open a flight

        # --- compute, then commit: nothing below can leave the flight half-updated ---
        peak = fl["peak_alt"]
        for v in peak_in:
            peak = _extend(peak, v, max)
        rssi_min = _extend(fl["rssi_min"], rssi, min)
        rssi_max = _extend(fl["rssi_max"], rssi, max)
        gaps, last_seq = fl["gaps"], fl["last_seq"]
        if seq is not None:            # a frame without SEQ consumed no sequence number
            if last_seq is not None:
                d = (seq - last_seq - 1) % 65536       # uint16 wraparound-aware
                # REORDER TOLERANCE (2026-08-25): a backwards or duplicate SEQ
                # (d in the upper half-window) is a reordering artifact — a
                # timestamp inversion upstream, never ~65k lost packets. Count
                # nothing and keep last_seq, so the next in-order frame
                # computes against the true high-water mark. Genuine uint16
                # wraparound lands in the lower half-window and still counts.
                if d < 32768:
                    gaps += d
                    last_seq = seq
            else:
                last_seq = seq

        fl.update(t_end_iso=received_at, t_end=t, packets=fl["packets"] + 1,
                  peak_alt=peak, rssi_min=rssi_min, rssi_max=rssi_max,
                  gaps=gaps, last_seq=last_seq)
        self._push_alt(src, t, alt)

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
        self._alt_hist.pop(fl["src"], None)   # next flight re-establishes its own baseline
        return Flight(
            flight_id=fl["flight_id"], src=fl["src"],
            t_start=fl["t_start_iso"], t_end=fl["t_end_iso"],
            stats={
                "peak_alt_ft": fl["peak_alt"],
                "duration_s": round(fl["t_end"] - fl["t_start"], 3),
                "packets_rx": fl["packets"],            # TELEMETRY frames only
                "beacons_rx": fl["beacons"],            # non-telemetry, segregated
                "packets_lost": fl["gaps"],
                "rssi_min": fl["rssi_min"],
                "rssi_max": fl["rssi_max"],
                "baseline_ft": fl["baseline_ft"],       # v2 AGL zero (retrospective)
                "baseline_n": fl["baseline_n"],         # samples used
            },
        )
