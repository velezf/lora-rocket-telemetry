# ADR 0003 — Field-time integrity: RTC-boot-restore + fail-closed ingest clock gate

- **Status:** Accepted (verified 2026-07-27 on a true Wi-Fi-OFF cold boot)
- **Date:** 2026-07-27
- **Relates to:** Epic 4 ingest ([ADR 0001](0001-packet-format-v1.md) is the payload it timestamps);
  hardens the earlier field-time-hardening work (`feat/field-time-hardening`). Complemented by the
  Pi 5 coin-cell hardware fallback (Option A, backlog) and inherited by Epic 8 (see Corollary).

## Context

The ground station timestamps every session and record from the system clock (time is injected at
the one radio owner; no consumer reads a clock). At boot that clock must already be correct — and
in the field, offline, it was not.

The 2026-07-13 boot (with Wi-Fi) exposed the gap. In order, at boot:

1. The kernel set the clock from the Pi 5's `rtc0` → **1970** (the Pi 5 has **no coin cell**).
2. `systemd-timesyncd` advanced it to its **saved-clock floor** = the last shutdown time.
3. **Nothing read the PiSugar RTC** (`0x68`, battery-backed, correct) into the system clock.

`apogee-ingest`'s old `year ≥ 2024` check passed on that stale floor and opened a **mis-dated
session** (`session-20260709T015114Z`, really Jul 13); only NTP later corrected it. **Offline, that
session would have been silently mis-dated** — a corrupt flight record with no warning. A
plausible-year clock is not, by itself, a trustworthy clock.

## Decision

Two coupled parts — a boot-time restore, and a gate that refuses to trust a floor.

**1. RTC-boot-restore (Option B, software).** A systemd oneshot `apogee-rtc-restore.service`
(`Type=oneshot`, `RemainAfterExit=yes`), ordered `After=pisugar-server.service` and — the essential
edge — `Before=apogee-ingest.service`. It reads the PiSugar RTC via the `pisugar-server` API
(`get rtc_time` → ISO-8601) and runs pure, host-tested decision logic (`ground/clock/rtc_restore.py`):

- `decide(rtc, sys)` returns `set` only when the system clock is **bogus** (`year < 2024`) or
  **grossly behind** the RTC — `(rtc − sys) > _FORWARD_THRESHOLD_S` (**120 s**), the floor case.
- It **never steps the clock backward**: an RTC more than the tolerance *behind* the system clock is
  treated as stale (`leave`, do not attest); a within-tolerance match is `clock-already-current`.
- On `set`, the runner calls `date -s` and drops the **trust marker** `/run/apogee-rtc-restored`.
- Audit events go to **journald only** — it never writes the session log, ops journal, or flights
  index (the one-writer invariant holds). Any failure → log and do nothing, never block boot.

**2. Fail-closed ingest clock gate.** `apogee-ingest`'s `ExecStartPre` is `ground/clock/gate.py`:

- `clock_trustworthy = (year ≥ 2024) AND (ntp_synced OR rtc_restored-marker)`. **A plausible-year
  timesyncd floor alone no longer passes.**
- It waits briefly for NTP or the marker, then **fails closed** (exit 1) — ingest never opens a
  session under an untrusted clock. `StartLimitIntervalSec=0` so it retries indefinitely (until NTP
  arrives or the operator attests) without tripping start-limit lockout.

**3. Operator escape hatch.** Dead RTC *and* no network would otherwise mean no ingest = a lost
flight. `ground/clock/attest_clock.py` lets the operator vouch for a hand-set clock. It is invoked
via the **`apogee-attest.service` oneshot** (same `WorkingDirectory=` as the restore unit), so the
range procedure is three consistent, **cwd-independent** commands:

```
sudo date -s '<YYYY-MM-DD HH:MM:SS>'    # set from a watch/phone
sudo systemctl start apogee-attest      # drops the trust marker (from the repo root, always)
sudo systemctl start apogee-ingest      # gate now passes on the marker
```

The bare `cd <repo> && python -m ground.clock.attest_clock` invocation is retained as **break-glass
only** (if the unit is unavailable) — it MUST run from the repo root, else `ground.clock` is not
importable (bench-found 2026-07-27). **Deploy:** install `apogee-attest.service` to
`/etc/systemd/system/` + `systemctl daemon-reload`; recreate on an SD rebuild alongside `gs-venv`
and the other units.

**Ordering rationale.** `Before=apogee-ingest` is the only edge that matters. We deliberately do
**not** order before `time-sync.target`: that risks an ordering cycle, and NTP re-stepping the clock
*after* us is harmless (it only refines a clock we already made correct).

## Consequences

- **The 07-13 failure cannot silently recur.** No session opens under a stale floor; the worst case
  offline is a *refusal to start* (loud, in the journal), never a silently mis-dated record.
- **Trade accepted:** dead RTC + no network ⇒ ingest waits for the operator to attest. Fail-closed
  beats silently-wrong for a flight archive. `StartLimitIntervalSec=0` means NTP arrival
  auto-recovers with no intervention; the escape hatch covers the fully-offline case.
- The marker lives in `/run` (tmpfs) — **per-boot by design**; each boot must re-establish trust.
- The escape hatch requires console/physical access **and a known-good external time source**
  (operator's watch/phone) — an accepted operational dependency.
- **Option A (complementary, backlog):** a coin cell on the Pi 5 RTC header (J5) so `rtc0` keeps
  time and the kernel sets a correct clock with no PiSugar/NTP. Cleanest hardware fallback;
  complements — does not replace — this software path.

## Corollary — Epic 8 (kids' handheld)

The Pi Zero 2 W has **no `rtc0` at all**, so Option A is impossible there and this software
RTC-boot-restore is the **only** field-time path. Epic 8 replicates `ground/clock/` against the
handheld's own RTC.

## Validation — 2026-07-27 Wi-Fi-OFF cold boot (PASS)

A true field simulation: fully powered off ~13 days, booted with Wi-Fi persistently soft-blocked and
**Ethernet physically unplugged until +15 min** — so no NTP could sync before the boot-time clock
decisions (the load-bearing condition: a live link at boot would make "gate passed on marker"
indistinguishable from "gate passed on NTP").

**The floor bug reproduced, then was defeated — the clock jumps 62 minutes mid-journal** as `date -s`
fires (`journalctl -u apogee-rtc-restore -b`):

```
2026-07-27T10:53:50-04:00 systemd[1]: Starting apogee-rtc-restore.service...
2026-07-27T10:53:51-04:00 python[641]: {"event":"rtc_restore","action":"set","reason":"sys-behind-rtc","rtc_time":"2026-07-27T11:56:09-04:00","sys_before":"2026-07-27T14:53:50Z"}
2026-07-27T11:56:09-04:00 python[641]: {"event":"rtc_restore","action":"marked","reason":"sys-behind-rtc"}
2026-07-27T11:56:09-04:00 systemd[1]: Finished apogee-rtc-restore.service.
```

The system came up at the timesyncd floor (`sys_before` = `14:53:50Z`, ~62 min stale); the PiSugar
RTC read the real `11:56:09`; Δ ≈ 3739 s ≫ 120 s → `action=set / reason=sys-behind-rtc`.

**Ingest opened a correctly-named session on the marker, not NTP** — first NTP sync landed ~15 min
later (when the cable went in), postdating **both** the clock-set and the session-open:

| Event | Time (EDT) |
|-------|-----------|
| rtc-restore `action=set`, clock stepped, marker dropped | `11:56:09` |
| `apogee-ingest` session `session-20260727T155616Z-8059ca.jsonl` opened | `11:56:16` |
| first NTP sync (Ethernet plugged at +15 min) | `12:11:13` |

**Verdict:** `action=set / reason=sys-behind-rtc` with `sys_before` ~1 h behind · rtc-restore ordered
before ingest · `/run/apogee-rtc-restored` present · gate passed on the marker (NTP still unsynced) ·
session correctly named · first NTP sync postdates both. **PASS.**

**RTC-hold criterion** — satisfied free by the hiatus: the PiSugar RTC kept correct wall-clock across
~13 days fully powered off at 69 % with no drain (read back `2026-07-27T10:45:47-04:00` on power-up).

## Appendix A — Full verbatim journal (rotation-proof capture)

Preserved because journald rotates; also raw material for the Stage-2 "KC3ZTQ RadioRocket V2" writeup.

`journalctl -u apogee-rtc-restore -b -o short-iso`:

```
2026-07-27T10:53:50-04:00 apogee-gs systemd[1]: Starting apogee-rtc-restore.service - Restore system clock from the PiSugar RTC before ingest...
2026-07-27T10:53:51-04:00 apogee-gs python[641]: {"type": "event", "event": "rtc_restore", "action": "set", "reason": "sys-behind-rtc", "rtc_time": "2026-07-27T11:56:09-04:00", "sys_before": "2026-07-27T14:53:50.362626+00:00", "received_at": "2026-07-27T14:53:50.362626+00:00"}
2026-07-27T11:56:09-04:00 apogee-gs python[641]: {"type": "event", "event": "rtc_restore", "action": "marked", "reason": "sys-behind-rtc", "rtc_time": "2026-07-27T11:56:09-04:00", "sys_before": "2026-07-27T14:53:50.362626+00:00", "received_at": "2026-07-27T14:53:50.362626+00:00"}
2026-07-27T11:56:09-04:00 apogee-gs systemd[1]: Finished apogee-rtc-restore.service - Restore system clock from the PiSugar RTC before ingest.
```

`journalctl -u apogee-ingest -b -o short-iso` (head):

```
2026-07-27T11:56:16-04:00 apogee-gs systemd[1]: Started apogee-ingest.service - Apogee ground telemetry ingest (single radio owner).
2026-07-27T11:56:16-04:00 apogee-gs python[3507]: [ingest] /home/rocketman/apogee-data/session-20260727T155616Z-8059ca.jsonl  allowed_sys=[7] known_src=[1, 2]
```

Session first line:

```
{"type":"event","received_at":"2026-07-27T15:56:16.546Z","event":"service_start","session":"session-20260727T155616Z-8059ca.jsonl","config":{"allowed_sys":[7],"known_src":[1,2],"callsign_binding":{},"silence_timeout_s":90}}
```

`journalctl -u systemd-timesyncd -b -o short-iso` (first server contact):

```
2026-07-27T10:53:49-04:00 apogee-gs systemd-timesyncd[346]: Network configuration changed, trying to establish connection.
2026-07-27T12:11:13-04:00 apogee-gs systemd-timesyncd[346]: Contacted time server 23.168.24.210:123 (0.debian.pool.ntp.org).
2026-07-27T12:11:13-04:00 apogee-gs systemd-timesyncd[346]: Initial clock synchronization to Mon 2026-07-27 12:11:13.170279 EDT.
```

Trust marker present: `/run/apogee-rtc-restored`, mtime `2026-07-27 11:56:09`.
