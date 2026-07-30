# Bench-artifact sessions — provenance register

**Append-only.** A standing record of ground-station session logs (`~/apogee-data/session-*.jsonl`
on `apogee-gs`) that were produced by **bench tests, not flights** — so a future reader (or a
`flights rebuild` sweep) does not mistake them for real telemetry. This is the single canonical
provenance list; add a row whenever a bench test opens a session, never restate it elsewhere.

Session logs live only on the Pi (not in this repo) and are disposable; this register is the
durable, version-controlled memory of what they were. Row format is stable:

| Session ID | Date (UTC) | What created it | Why it is not flight data |
|------------|------------|-----------------|---------------------------|
| `session-20260709T015114Z-4a1ab4` | 2026-07-09 (filename) — **really 2026-07-13** | The pre-fix mis-dated boot: kernel came up 1970, `systemd-timesyncd` restored its saved-clock floor, the old year-only gate opened a session under the stale floor. The finding that motivated `feat/rtc-boot-restore` / [ADR 0003](adr/0003-rtc-boot-restore-clock-gate.md). | **Wrong wall-clock** (filename is ~4 days early). Holds **1493 real packets but 0 flight events** — real over-the-air RF that never tripped launch detect, so `rebuild` yields no flight. "Real RF, never a flight" is the detail that would mislead a reader who sees the packet count. |
| `session-20260727T182808Z-151b2d` | 2026-07-27 | The `apogee-attest` escape-hatch bench validation ([ADR 0003](adr/0003-rtc-boot-restore-clock-gate.md)): clock hand-set by the operator, marker dropped via `attest_clock`, ingest started on the marker. | **Synthetic clock** (hand-set, not RTC/NTP) and **empty** — only `service_start`/`service_stop`, 0 packets, 0 flights. A gate-path artifact, not telemetry. |
| `session-20260730T181333Z-266cc9` | 2026-07-30 | Button graceful-shutdown test A (USB-C double-tap). | `service_start` + 1 error packet + `service_stop`. Button-test byproduct, 0 flights — proves a clean close, not telemetry. |
| `session-20260730T182930Z-3915db` | 2026-07-30 | Button test B (micro-USB button, ~5 s hold). | `service_start` + `service_stop` (also a clean close — see wiring-doc button notes). Button-test byproduct, 0 flights. |

_Note on the normal-path session `session-20260727T182911Z-96f90d` (opened by the post-attest
restore reboot): a legitimate empty service session, not a bench artifact — no row needed._
