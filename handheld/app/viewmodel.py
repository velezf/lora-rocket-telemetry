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

    def observe(self, pkt, rssi_dbm: float, mono: float) -> None:
        if not pkt.ok:
            return
        if pkt.fields.get("SYS") not in self._allowed_sys:
            self.foreign_sys += 1
            return

        st = pkt.fields.get("St")
        alt = pkt.fields.get("ALT")
        maxft = pkt.fields.get("Max")

        # liftoff is the observed TRANSITION out of pad state — a model that
        # first hears the sky mid-flight has no liftoff moment to announce
        if st == 1 and self._st == 0:
            self._liftoff_mono = mono
        if st == 2:
            self._apogee_revealed = True

        if alt is not None:
            self._alt_ft = alt
            if self._peak_ft is None or alt > self._peak_ft:
                self._peak_ft = alt
        # the sled's own running max is authoritative: RF loss can hide the
        # true peak from a receive-only listener
        if maxft is not None and (self._peak_ft is None or maxft > self._peak_ft):
            self._peak_ft = maxft

        if st is not None:
            self._st = st
        self._rssi = rssi_dbm
        self._last_mono = mono

    def snapshot(self, mono: float) -> View:
        if self._last_mono is None:
            return View("idle", None, None, None, None, None, False, False)
        age = mono - self._last_mono
        mode = "stale" if age > self._stale_s else "live"
        banner = (self._liftoff_mono is not None
                  and mono - self._liftoff_mono <= self._banner_s)
        return View(mode, self._alt_ft, self._peak_ft, self._st, self._rssi,
                    round(age, 3), banner, self._apogee_revealed)
