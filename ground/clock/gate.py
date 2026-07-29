"""Ingest clock-trust gate (fail-closed) — apogee-ingest's ExecStartPre.

Proceed (exit 0) only when the clock is trustworthy: NTP-synced OR set from the RTC
(the `/run/apogee-rtc-restored` marker). A plausible-year systemd-timesyncd floor ALONE
no longer passes (the bug that opened a mis-dated session). Waits briefly for NTP/marker,
then FAILS CLOSED (exit 1) so ingest never opens a session under a stale clock. Field
escape hatch when the RTC is dead and there's no network: `ground.clock.attest_clock`.
"""
import os
import subprocess
import sys
import time
from datetime import datetime

from ground.clock.rtc_restore import clock_trustworthy

MARKER = "/run/apogee-rtc-restored"


def ntp_synced() -> bool:
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() == "yes"
    except (OSError, subprocess.SubprocessError):
        return False


def main(timeout_s: int = 30) -> int:
    for _ in range(timeout_s):
        if clock_trustworthy(ntp_synced(), os.path.exists(MARKER), datetime.now().year):
            return 0
        time.sleep(1)
    print("clock-gate: UNTRUSTED — no NTP sync and no RTC-restore marker; refusing to "
          "open a session under a stale clock. Field escape hatch (set the clock, then "
          "`systemctl start apogee-attest`, then `apogee-ingest`) — see the procedure in "
          "docs/adr/0003-rtc-boot-restore-clock-gate.md.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
