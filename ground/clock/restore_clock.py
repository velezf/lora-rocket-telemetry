"""Pi-only runner: set the system clock from the PiSugar RTC at boot.

Read the RTC via the pisugar-server API (TCP `get rtc_time` -> ISO-8601), run the pure
decision logic, and — only when the system clock is bogus or grossly behind the RTC —
set it and drop the trust marker `/run/apogee-rtc-restored`. Emits its audit event to
STDOUT (journald) ONLY: it never writes the session log, ops journal, or flights index
(one-writer invariant). Any failure -> log + do nothing (never block boot; exit 0).

Runs as a systemd oneshot ordered After=pisugar-server.service, Before=apogee-ingest.service.
"""
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

from ground.clock.rtc_restore import extract_rtc_time, parse_rtc, decide, audit_event

MARKER = "/run/apogee-rtc-restored"


def _log(ev: dict) -> None:
    print(json.dumps(ev), flush=True)   # -> journald; NOT session/ops/index


def read_pisugar_rtc(host: str = "127.0.0.1", port: int = 8423,
                     timeout: float = 3.0, wait_s: int = 15):
    """Poll pisugar-server for the RTC. `After=pisugar-server` orders the service
    *start*, not its socket readiness — at boot the API may not be listening yet, so
    retry until it answers with a valid reading, or give up after wait_s (-> None,
    leaving the gate to fail closed / the operator to attest)."""
    for _ in range(wait_s):
        try:
            with socket.create_connection((host, port), timeout) as s:
                s.sendall(b"get rtc_time\n")
                iso = extract_rtc_time(s.recv(256).decode(errors="replace"))
            if iso:
                return iso
        except OSError:
            pass
        time.sleep(1)
    return None


def main() -> int:
    now = datetime.now(timezone.utc)
    rtc = parse_rtc(read_pisugar_rtc() or "")
    action, reason = decide(rtc, now)
    _log(audit_event(rtc, now, action, reason, now.isoformat()))

    # Drop the trust marker when a VALID RTC established the clock (we set it, or it
    # already confirmed the current clock). Never on backstep / invalid / bogus-read.
    attested = action == "set" or reason == "clock-already-current"
    if action == "set" and rtc is not None:
        try:
            subprocess.run(["date", "-s", rtc.isoformat()], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            _log(audit_event(rtc, now, "error", f"date-set-failed: {exc}", now.isoformat()))
            return 0        # never block boot
    if attested:
        try:
            open(MARKER, "w").close()
            _log(audit_event(rtc, now, "marked", reason, now.isoformat()))
        except OSError as exc:
            _log(audit_event(rtc, now, "error", f"marker-failed: {exc}", now.isoformat()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
