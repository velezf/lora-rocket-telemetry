"""Pure view-model for the kids' handheld display (Epic 8.2).

Decoded v1 frames + injected monotonic time in; an immutable `View` snapshot
out. No I/O, no clocks, no radio — the render/RX glue threads consume
`snapshot()`, the same view-model-snapshot seam the ground OLED uses
(see docs/RESUME.md "Previous session's handoff", item 3).

SYS filtering mirrors the ground ingest: the allowlist is config with the
same default (see `ground/ingest/core.py` — default {7}, per ADR 0001).
Foreign-SYS frames are dropped but counted, never silently.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class View:
    mode: str                    # "idle" | "live" | "stale"
    alt_ft: int | None
    peak_ft: int | None
    st: int | None
    rssi_dbm: float | None
    age_s: float | None          # seconds since last accepted frame
    liftoff_banner: bool
    apogee_reveal: bool
    battery_pct: int | None = None   # handheld's own charge (pisugar-server)


class HandheldModel:
    def __init__(self, liftoff_banner_s: float = 3.0, stale_s: float = 5.0,
                 allowed_sys=frozenset({7})):
        self._banner_s = liftoff_banner_s
        self._stale_s = stale_s
        self._allowed_sys = frozenset(allowed_sys)
        self.foreign_sys = 0

        self._last_mono: float | None = None
        self._alt_ft: int | None = None
        self._peak_ft: int | None = None
        self._st: int | None = None
        self._rssi: float | None = None
        self._liftoff_mono: float | None = None
        self._apogee_revealed = False

        # AGL pad baseline — the SAME shared function the ground live path
        # locks at flight_open (ground/flights/baseline.py). Rolling while
        # St:0, FROZEN at the observed liftoff; None -> raw fallback (a
        # handheld powered on mid-flight has no pad history to zero from).
        self._pad_hist: list[tuple[float, int]] = []
        self._baseline: int | None = None
        self._baseline_frozen = False
        self._battery_pct: int | None = None

    def set_battery(self, pct: int | None, mono: float) -> None:
        """Latest gauge reading; None (a failed read) keeps the last known —
        a stale charge number beats a vanishing one on a slow-moving value."""
        if pct is not None:
            self._battery_pct = pct

    def observe(self, pkt, rssi_dbm: float, mono: float) -> bool:
        """Fold one decoded frame in. Returns True iff the frame was accepted."""
        if not pkt.ok:
            return False
        if pkt.fields.get("SYS") not in self._allowed_sys:
            self.foreign_sys += 1
            return False

        st = pkt.fields.get("St")
        alt = pkt.fields.get("ALT")
        maxft = pkt.fields.get("Max")

        # liftoff is the observed TRANSITION out of pad state — a model that
        # first hears the sky mid-flight has no liftoff moment to announce
        if st == 1 and self._st == 0:
            self._liftoff_mono = mono
            self._baseline_frozen = True
        if st == 2:
            self._apogee_revealed = True

        if st == 0 and alt is not None and not self._baseline_frozen:
            from ground.flights.baseline import pad_baseline, trim_history
            self._pad_hist.append((mono, alt))
            self._pad_hist = trim_history(self._pad_hist)
            # rolling verdict, None included: a pad that stops being quiet
            # stops being a zero (the stability gate is the whole point)
            self._baseline, _ = pad_baseline(self._pad_hist)

        if alt is not None:
            agl = alt - self._baseline if self._baseline is not None else alt
            self._alt_ft = agl
            if st == 0:
                # pad: the peak follows the (rolling) zero — a rocket that has
                # never moved has no peak to report
                self._peak_ft = max(0, agl) if self._baseline is not None else 0
            elif self._peak_ft is None or agl > self._peak_ft:
                self._peak_ft = agl
        # in flight the sled's own running max is authoritative (RF loss can
        # hide the true peak from a receive-only listener); on the pad it is
        # an artifact by contract — 0 until the first in-flight sample
        # (firmware/src/main.cpp:402) — and must be ignored
        if maxft is not None and st is not None and st != 0:
            m_agl = maxft - self._baseline if self._baseline is not None else maxft
            if self._peak_ft is None or m_agl > self._peak_ft:
                self._peak_ft = m_agl

        if st is not None:
            self._st = st
        self._rssi = rssi_dbm
        self._last_mono = mono
        return True

    def snapshot(self, mono: float) -> View:
        if self._last_mono is None:
            return View("idle", None, None, None, None, None, False, False,
                        self._battery_pct)
        age = mono - self._last_mono
        mode = "stale" if age > self._stale_s else "live"
        banner = (self._liftoff_mono is not None
                  and mono - self._liftoff_mono <= self._banner_s)
        return View(mode, self._alt_ft, self._peak_ft, self._st, self._rssi,
                    round(age, 3), banner, self._apogee_revealed,
                    self._battery_pct)
