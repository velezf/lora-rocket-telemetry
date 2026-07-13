"""Pure RTC-boot-restore logic (feat/rtc-boot-restore).

At boot the Pi 5's rtc0 reads 1970 (no coin cell) and systemd-timesyncd restores its
saved-clock floor (= last shutdown); nothing reads the PiSugar RTC into the system
clock, so apogee-ingest's year>=2024 gate opened a mis-dated session. These pure
functions (a) decide whether to set the system clock from the PiSugar RTC at boot, and
(b) harden the ingest trust gate so a plausible-year floor ALONE no longer passes.

The read mechanism (pisugar-server API `get rtc_time` -> ISO-8601) and the actual
clock set live in a thin Pi-only runner; this module is clock-free and host-tested.
"""
from datetime import datetime

_MIN_YEAR = 2024
_MAX_YEAR = 2100
_FORWARD_THRESHOLD_S = 120   # only "set" when the system clock lags the RTC by > this


def parse_rtc(s):
    """pisugar-server's ISO-8601 RTC reading -> aware datetime, or None if unparseable."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.strip())
    except (ValueError, TypeError):
        return None


def is_valid(dt) -> bool:
    """A sane wall-clock reading: present and within [2024, 2100] (rejects 1970/epoch)."""
    return dt is not None and _MIN_YEAR <= dt.year <= _MAX_YEAR


def decide(rtc, sys, forward_threshold_s: float = _FORWARD_THRESHOLD_S):
    """Return (action, reason) — whether to set the system clock from the PiSugar RTC.

    Set only when the system clock is bogus, or grossly behind the RTC (the
    timesyncd-floor case). NEVER step the clock backward: if the RTC is behind the
    system clock (e.g. NTP already corrected it), leave it alone.
    """
    if not is_valid(rtc):
        return ("leave", "rtc-invalid")
    if sys.year < _MIN_YEAR:
        return ("set", "sys-clock-bogus")
    delta = (rtc - sys).total_seconds()
    if delta > forward_threshold_s:
        return ("set", "sys-behind-rtc")                    # the floor case
    if delta < 0:
        return ("leave", "rtc-behind-sys-no-backstep")      # never step backward
    return ("leave", "clock-already-current")


def audit_event(rtc, sys_before, action, reason, received_at) -> dict:
    """The rtc_restore advisory event (same shape as other session-log events)."""
    return {
        "type": "event",
        "event": "rtc_restore",
        "action": action,
        "reason": reason,
        "rtc_time": rtc.isoformat() if rtc is not None else None,
        "sys_before": sys_before.isoformat() if sys_before is not None else None,
        "received_at": received_at,
    }


def clock_trustworthy(ntp_synced: bool, rtc_restored: bool, year: int) -> bool:
    """Hardened ingest gate: a plausible year ALONE is not enough — require that the
    clock was either NTP-synced or set from the RTC (the marker). Otherwise the
    timesyncd saved-clock floor silently satisfies the old year>=2024 check."""
    return year >= _MIN_YEAR and (ntp_synced or rtc_restored)
