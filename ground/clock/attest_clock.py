"""Field escape hatch — operator attests the system clock is correct.

The ingest gate is fail-closed: a dead RTC + no network at the range would otherwise
mean no ingest = lost flight. After the operator has set the clock by hand, this drops
the `/run/apogee-rtc-restored` marker so the gate trusts the clock and apogee-ingest
will start. Audit to STDOUT (journald) only.

Field procedure (primary) — invoked via the apogee-attest.service oneshot, which carries
WorkingDirectory=<repo> so this module is always importable (never cwd-dependent):

    sudo date -s '<YYYY-MM-DD HH:MM:SS>'
    sudo systemctl start apogee-attest
    sudo systemctl start apogee-ingest

Break-glass only (if the apogee-attest unit is unavailable) — MUST run from the repo root,
else `python -m ground.clock.attest_clock` is not importable:

    sudo date -s '<YYYY-MM-DD HH:MM:SS>'
    cd /home/rocketman/lora-rocket-telemetry && \\
        sudo /home/rocketman/gs-venv/bin/python -m ground.clock.attest_clock
    sudo systemctl start apogee-ingest
"""
import json
import sys
from datetime import datetime, timezone

from ground.clock.rtc_restore import audit_event

MARKER = "/run/apogee-rtc-restored"


def main() -> int:
    now = datetime.now(timezone.utc)
    try:
        open(MARKER, "w").close()
    except OSError as exc:
        print(f"attest-clock: could not write {MARKER}: {exc} (run with sudo?)", file=sys.stderr)
        return 1
    print(json.dumps(audit_event(now, now, "attested", "operator-manual", now.isoformat())),
          flush=True)
    print(f"clock attested at {now.isoformat()} — marker dropped. "
          f"Now: sudo systemctl start apogee-ingest", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
