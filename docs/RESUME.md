# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: 2026-06-30 (Claude, on Mac + Pi 5 over SSH)._

## Where we are

Foundations are down. Epic 1 (Mac PlatformIO toolchain) is built and merged; the v1
packet contract — the keystone everything downstream depends on — is **locked and
published** as ADR 0001. The Epic 2 ground station (`apogee-gs`) is now on the network:
OS baseline, Wi-Fi-on-boot, and Pi Connect are done; only the radio/UPS hardware tasks
remain. Next up is the Epic 3 firmware build (all host-testable; no board needed yet).
Epic 8 has its platform groundwork merged.

## Ground station (`apogee-gs`) — access

- **SSH:** `ssh rocketman@apogee-gs.local` (key auth, passwordless sudo).
- **Pi Connect:** signed in as device `apogee-gs` (`rpi-connect-lite`, remote shell;
  no screen sharing — headless). Reachable from anywhere, not just the local network.
- **OS:** Raspberry Pi OS 64-bit, **Trixie / Debian 13** (not Bookworm). Python 3.13.
- **Wi-Fi:** home **WideRoad** (priority 0) first, **iPhone 17 hotspot** fallback
  (priority −10, infinite retry, persistent NM keyfile). Networking is netplan-rendered
  → NetworkManager. _(Hotspot secret lives only on the Pi, never in this repo.)_

## Epic status

| Epic | Status |
|------|--------|
| 1 — PlatformIO dev env (Mac) | ✅ **Done & published** (1.1–1.3). 1.4 upload smoke **deferred — hardware-gated** (no Feather M0). |
| 2 — Pi 5 ground-station bring-up | 🟡 **2.1 + 2.2 done** (OS baseline, updates, EEPROM, headless SSH, I²C+SPI enabled; Wi-Fi home→hotspot, cold-boot rejoin verified) **+ Pi Connect**. **2.3 Claude Code** and **2.4 git deploy key** deferred. **2.5 radio RX / 2.6 PiSugar** hardware-blocked. Hotspot fallback configured but not field-verified. |
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

1. **Finish Epic 2 software tasks** on `apogee-gs`: **2.3** Claude Code (native installer)
   and **2.4** GitHub pull path (generate an SSH deploy key on the Pi, add it to the repo,
   clone). Both quick; no hardware needed.
2. Start **`feat/sled-firmware-v1`** for Epic 3, RED→GREEN per task, in dependency order:
   3.7 conversions → 3.5 launch → 3.6 apogee → 3.4 `St`+`SEQ` → 3.3 `SYS`/`SRC` →
   3.2 packet encoder (asserts ADR golden vector) → 3.1a port to `src/` (compile-only,
   `pio run -e feather_m0_tx`). Each pure unit obeys the `lib/` purity rule.
3. **Hardware day (batched, needs the Feather M0):** 1.4 upload smoke + 3.1b flash &
   parity diff vs. the V1 `.ino`.
4. **Field test (away from home Wi-Fi):** confirm `apogee-gs` falls back to the iPhone
   hotspot (`iwgetid -r` / `nmcli` should show the hotspot SSID).

## Hardware gating

No Feather M0 on hand. Everything in Epic 3 except 3.1b is native/host-testable on the
Mac or Pi. The first `pio run -e feather_m0_tx` (3.1a) also doubles as the first real
compile of Epic 1's pinned `lib_deps` against the SAMD target.
