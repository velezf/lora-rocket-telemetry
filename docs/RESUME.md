# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: 2026-06-30 (Claude, on Mac)._

## Where we are

Foundations are down. Epic 1 (Mac PlatformIO toolchain) is built and merged; the v1
packet contract — the keystone everything downstream depends on — is **locked and
published** as ADR 0001. Next up is the Epic 3 firmware build (all host-testable; no
board needed yet). Epic 2 (Pi 5 ground station) is being brought up in parallel on the
Pi itself, and Epic 8 has its platform groundwork merged.

## Epic status

| Epic | Status |
|------|--------|
| 1 — PlatformIO dev env (Mac) | ✅ **Done & published** (1.1–1.3). 1.4 upload smoke **deferred — hardware-gated** (no Feather M0). |
| 2 — Pi 5 ground-station bring-up | 🔧 In progress on the Pi 5 (parallel session). Status not fully known on the Mac side — confirm before depending on it. |
| 3 — Sled TX firmware + contract | 🟡 **Contract locked & published (ADR 0001).** Firmware build not started. |
| 4 — Ground service (decode/log/dash/web/OLED) | ⏳ Not started. 4.1 decoder can begin against the published ADR. |
| 5 — 9-DoF integration | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

None. The ADR/plan, the tag-namespace appendix, and the `CLAUDE.md` + `RESUME.md`
docs are all merged to `main` and pushed. Next branch will be `feat/sled-firmware-v1`
(Epic 3).

## Locked decisions

- **Packet format v1** ([ADR 0001](adr/0001-packet-format-v1.md)): keyed `KEY:VALUE`
  ASCII, leading `V:1`; time token `MET:12`; **no app-layer checksum** (rely on LoRa PHY
  CRC); `SYS` default `7`; `SRC` registry `1=sled, 2=lander`. Battery *status* derived on
  the ground (payload carries raw `Batt:` volts only).
- **ADR numbering:** global `docs/adr/` **and** per-component logs (e.g.
  `handheld/docs/adr/`) are both fine.

## Immediate next steps

1. Start **`feat/sled-firmware-v1`** for Epic 3, RED→GREEN per task, in dependency order:
   3.7 conversions → 3.5 launch → 3.6 apogee → 3.4 `St`+`SEQ` → 3.3 `SYS`/`SRC` →
   3.2 packet encoder (asserts ADR golden vector) → 3.1a port to `src/` (compile-only,
   `pio run -e feather_m0_tx`). Each pure unit obeys the `lib/` purity rule.
2. **Hardware day (batched, needs the Feather M0):** 1.4 upload smoke + 3.1b flash &
   parity diff vs. the V1 `.ino`.

## Hardware gating

No Feather M0 on hand. Everything in Epic 3 except 3.1b is native/host-testable on the
Mac or Pi. The first `pio run -e feather_m0_tx` (3.1a) also doubles as the first real
compile of Epic 1's pinned `lib_deps` against the SAMD target.
