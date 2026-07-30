# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: 2026-07-27 (Claude, on Mac + Pi 5 over Ethernet) — RTC-boot-restore VERIFIED on a
true Wi-Fi-OFF cold boot (overnight cold-boot physical task CLOSED; see Physical tasks). Branch
`feat/rtc-boot-restore` still unmerged/unpushed, awaiting the `--no-ff` merge against the full
159-test suite. Still parked from 2026-07-08: the flights page mock on pages-repo branch
`feat/flights-section` awaiting Frank's review→merge→push, then Claude tags `v1.0-portfolio-genesis`._

## Where we are

**Epics 1–3 complete; Epic 4 (ground service) substantially built and merged.** Epic 1
(Mac PlatformIO) done, 1.4 upload proven on the Feather M0. The v1 packet contract is
locked as ADR 0001. Epic 2 ground station (`apogee-gs`) up: peripherals wired, native LoRa
RX driver (`ground/rx/`, raw spidev+lgpio; ADR 0002), PiSugar shutdown. Epic 3: the sled TX
emits ADR v1, e2e-verified against the ground driver + decoder.

**Epic 4 — 4.1 decoder, 4.2 ingest service, and 4.3 flight logging are all merged.** A single
radio-owning `apogee-ingest` **systemd service** (enabled, reboot-surviving): SX127x driver →
decoder → append-only JSONL session log + per-`(SYS,SRC)` link stats + foreign-traffic &
Part-97 callsign policy + **live flight detection** (advisory `flight_open`/`flight_close`
events). Plus an offline **flights CLI** (`rebuild`/`list`/`annotate`/`close`/`open`/`export`)
over a three-files/one-writer model (session ← service, ops journal ← CLI, index ← derivation).
**Field-time hardening** landed too: PiSugar RTC initialized + `auto_rtc_sync`, systemd clock
gate, and monotonic silence/duration deltas (immune to wall-clock steps); session filenames
are collision-proof. **4.4 dashboard + 4.6 status OLED are now done, merged, and deployed**
— live Flask/Chart.js dashboard (density pass: header callsign, per-SRC flight badge + live
age, T+, RSSI sparkline, events feed, health line) + SSD1306 status OLED on `0x3d`, both on a
per-SRC **AGL pad baseline** (ALT−baseline while `St:0`; raw ALT untouched in records; resets
on `flight_close`). Bench-verified on `apogee-gs` against live sled telemetry. **Epic 4
remaining: 4.5 web publish only, gated on the first real flight.** Epic 8 groundwork merged.

## Ground station (`apogee-gs`) — access

- **SSH:** `ssh rocketman@apogee-gs.local` (key auth, passwordless sudo).
- **Pi Connect:** signed in as device `apogee-gs` (`rpi-connect-lite`, remote shell;
  no screen sharing — headless). Reachable from anywhere, not just the local network.
- **Claude Code:** installed (`2.1.197`), on PATH (`~/.local/bin`), **authenticated** via
  `claude auth login` (claude.ai, Max). Headless `claude -p` works.
- **OS:** Raspberry Pi OS 64-bit, **Trixie / Debian 13** (not Bookworm). **Python 3.13.5**
  (`/usr/bin/python3`), `venv` works. No system `pip` (PEP 668 — use venv). **The
  `apogee-ingest` service runs from `~/gs-venv`** (`ExecStart`), the one env with all ground
  deps: `luma.oled`+`pillow` (pip) and `flask`/`spidev`/`lgpio` (via `--system-site-packages`).
  **System `python3` is no longer sufficient** — an SD-card rebuild must recreate `~/gs-venv`
  (`--system-site-packages`) with `luma.oled`. **`uv` not yet installed**.
- **Repo:** cloned at `~/lora-rocket-telemetry` via a **read-only deploy key** (`apogee-gs`);
  `git pull` works (Pi pulled to current `main`).
- **Wi-Fi:** home **WideRoad** (priority 0) first, **iPhone 17 hotspot** fallback
  (priority −10, infinite retry, persistent NM keyfile). Networking is netplan-rendered
  → NetworkManager. _(Hotspot secret lives only on the Pi, never in this repo.)_

## Wired peripherals (bench-verified 2026-07-07)

| Device | Bus | Address / CS | Notes |
|--------|-----|--------------|-------|
| RFM96 LoRa radio | SPI0 | **CE1** (`/dev/spidev0.1`, pin 26); RESET GPIO25 (pin 22) | `RegVersion 0x12`. **Not CE0.** |
| OLED (Adafruit 938, SSD1306 128×64) | I²C-1 | `0x3d` | driven via `~/gs-venv` + **`luma.oled`** |
| PiSugar 3 Plus UPS | I²C-1 | `0x57` batt, `0x68` RTC | `pisugar-server`; auto-shutdown at 5% / 30 s |
| Front-panel LEDs ×6 | GPIO | `5,6,13,26,12,16` (L→R: grn×3, red, blu×2) | active-high; bring-up via `ground/tools/led_check.py` |
| Sled 9-DoF (bench, Epic 5.1) | I²C | LSM6DSOX `0x6a`, LIS3MDL `0x1c` | on the sled's STEMMA QT bus alongside BMP390 `0x77` / ADXL375 `0x53` |

**Native LoRa RX** = the repo's `ground/rx/` **SX127x driver** (raw `spidev`+`lgpio`,
host-tested against a fake SPI, CRC-enforcing, RadioHead-header aware). **Blinka rejected —
[ADR 0002](adr/0002-ground-rx-driver-spidev.md)** (RPi.GPIO won't run on BCM2712). OLED uses
`luma.oled`; LEDs use `gpiozero`/lgpio — the whole ground stack is Blinka-free. `rocketman`
is in `spi`/`i2c`/`gpio` groups; `i2cdetect` is in `/usr/sbin`. **Authoritative pin map:**
[`docs/ground-station-wiring.md`](ground-station-wiring.md).

## Hardware state (bench, 2026-07-07)

- **All three nodes built and on the bench**, none yet enclosed:
  - **Sled** — Feather M0 + RFM95 + BMP390 `0x77` + ADXL375 `0x53`, now with the **9-DoF
    LSM6DSOX `0x6a` + LIS3MDL `0x1c` chained on**; runs the ADR v1 TX firmware.
  - **Lander** (KB2040 + 2nd RFM96) and **handheld** (Pi Zero 2 W + LoRa/OLED bonnet) —
    built, on bench; firmware not started (Epics 7 / 8).
- **Ground station** — Pi 5 in **benchtop config, not yet boxed** (radio/OLED/PiSugar/LEDs wired).
- **9-DoF** I²C-smoked (Epic 5.1 evidence — WHO_AM_I `0x6C`/`0x3D`, sane gyro/mag reads). Its
  libraries are **NOT in `platformio.ini` yet** — Epic 5 owns adding `Adafruit_LSM6DSOX`/`_LIS3MDL`.

## Epic status

| Epic | Status |
|------|--------|
| 1 — PlatformIO dev env (Mac) | ✅ **Done.** 1.1–1.3 + **1.4 upload smoke proven** on the Feather M0 (SAM-BA upload + serial heartbeat). |
| 2 — Pi 5 ground-station bring-up | ✅ **CLOSED.** OS/SSH/Wi-Fi/Claude Code/deploy-key clone; radio SPI0/CE1, OLED 0x3d, PiSugar batt+RTC, 6 panel LEDs; **2.5 RX driver** (`ground/rx/`); **2.6 low-battery auto-shutdown** (+ wake-on-charge complement). **2.2 hotspot fallback field test** carried as the single open **physical validation** (deferred, not blocking — same pattern as the overnight cold-boot item; run post-merge, doubling as the marker-vs-NTP clock check); panel-LED *functions* → Epic 4. |
| 3 — Sled TX firmware + contract | ✅ **Complete.** ADR 0001 locked; encoder/launch/apogee/conversions as host-tested `lib/` units; `src/main.cpp` emits **ADR v1** (`V:1 SYS:7 SRC:1 …`) with live SYS/SRC/SEQ/St/MET (**B4/B5 folded into the integration commit**); **e2e verified** — sled→Pi driver, **22/22 ADR-OK**, 0 CRC errors. |
| 4 — Ground service (decode/log/dash/web/OLED) | 🟢 **4.1–4.4 + 4.6 done & merged.** 4.1 decoder (`ground/decode/`); 4.2 **ingest** (`ground/ingest/` + `apogee-ingest.service` — radio owner → JSONL log + `LinkStats` + foreign-SYS/unknown-SRC + Part-97 callsign audit); 4.3 **flight logging** (`ground/flights/` — journal segmentation, multi-bird, export, CLI; index = f(session, ops)); **4.4 dashboard** (Flask + Chart.js, immutable snapshots, density pass) + **4.6 OLED** (`luma.oled` `0x3d`) on a per-SRC **AGL pad baseline**, both bench-verified live and **flown once** (`2026-07-08-F1`, real-RF golden fixture). **AGL baseline v2** merged: pure `pad_baseline()` (stability-gated trailing window) shared by live + derive — the zero **locks at flight_open**, unlocks at close, and `baseline_ft`+`baseline_n` are stored per flight in the index (auditable, reproduces on rebuild). Full ground suite 159 tests (incl. `feat/rtc-boot-restore`). **Remaining: 4.5 web publish only.** |
| 5 — 9-DoF integration | 🟡 **5.1 hardware evidence done** (LSM6DSOX 0x6a + LIS3MDL 0x1c on the sled bus; WHO_AM_I 0x6C/0x3D; sane gyro/mag). 5.2–5.4 not started; `Roll`/`Spin` reserved (ADR 0001 App. A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

**None open.** `feat/rtc-boot-restore` merged into `main` via `--no-ff` (RTC-boot-restore +
fail-closed clock gate + apogee-attest escape hatch; ADR 0003; verified on a Wi-Fi-OFF cold
boot) — **merged locally, NOT yet pushed to `origin/main`** (awaiting Frank's push gate).
Recent merged branches: `feat/status-oled` (4.4 dashboard density + 4.6 OLED + AGL baseline),
`feat/ground-decoder`, `feat/ingest-{linkstats,records,flights-model,service}`,
`feat/callsign-id`, `feat/flight-logging` (+ earlier Epic 1–3 branches).

## Locked decisions

- **Packet format v1** ([ADR 0001](adr/0001-packet-format-v1.md)): keyed `KEY:VALUE` ASCII,
  leading `V:1`; `MET` time token; **no app-layer checksum** (rely on LoRa PHY CRC); `SYS`
  default `7`; `SRC` `1=sled, 2=lander`; additive tags tolerated, unknown tags ignored.
  Human-readable index: [`docs/telemetry-dictionary.md`](telemetry-dictionary.md).
- **Ground RX = raw spidev + lgpio** ([ADR 0002](adr/0002-ground-rx-driver-spidev.md)),
  Blinka rejected on Pi 5.
- **Field-time integrity** ([ADR 0003](adr/0003-rtc-boot-restore-clock-gate.md)):
  `apogee-rtc-restore` oneshot reads the PiSugar RTC into the system clock at boot
  (`Before=apogee-ingest`); ingest's clock gate is **fail-closed** — `year≥2024 AND (NTP OR
  RTC-restore marker)`, so a plausible-year timesyncd floor alone no longer passes. Operator
  escape hatch = `attest_clock`. Verified on a Wi-Fi-OFF cold boot (2026-07-27).
- **Ground service (Epic 4):** one radio-owning process fans out
  `Observation(received_at, rssi, packet)` to consumers — **time is injected, no consumer
  reads a clock.** Three files, one writer each: session JSONL (service), ops journal (CLI),
  flights index (derivation); **index = pure f(session, ops)**; a **manual close/open beats
  the silence timeout.** Foreign-SYS / unknown-SRC counted + logged as advisory events,
  **never** into stats/flights (SYS allowlist + known-SRC are field config, not repo
  constants). Flight **close = 90 s silence or manual CLI** (auto-landed deferred — no St
  code). **Dashboard = Flask + Chart.js** (live); **4.5 flight pages = Quarto + pandas +
  Plotly → velezf.github.io** (one permalink per flight).
- **ADR numbering:** global `docs/adr/` and per-component logs both fine.

## Epic 6 firmware riders (deferred — additive; each re-runs the e2e gate)

1. **`St:3` = landed** — a landed flight-state code so the ground can auto-close a flight on
   landed (today it's 90 s silence + manual only — there is no landed signal).
2. **SRC per-unit build config** (`-DSRC_ID` per device env) — never a shared constant; two
   sleds from one repo must not both claim `SRC:1`.
3. **±10 % TX-interval jitter** — anti-lockstep for simultaneous birds.
4. **Part-97 station ID** — `CALL:<callsign>` at TX start / ≤9.5 min / graceful shutdown,
   per-unit `-DCALLSIGN`. Ground side (decoder fixture + ingest `id` audit + CALL↔SYS
   binding) already merged; the **lander (Epic 7) inherits the ID-timer obligation.**
5. **`BAT` battery go/no-go tag** — a derived pad-check go/no-go indicator to surface on the
   dashboard/OLED (raw volts already ride `Batt:`; this is the launch-readiness signal).
6. **St-dependent TX rate** — fast in boost/descent, slow on pad/landed, for flight-record
   resolution. **Coupled to detection:** today the ADXL is read *once per TX loop* (`delay(1000)`
   in `firmware/src/main.cpp` — **launch detect samples at the 1 Hz TX cadence, no FIFO/ISR**),
   so a faster boost-phase TX rate *also* sharpens launch/apogee detection and MET granularity.
   **Do the duty-cycle / airtime math first** (ISM-band airtime budget + LoRa ToA at the chosen
   SF/BW) before picking rates; a cleaner design may decouple detection sampling (fast, FIFO/ISR)
   from TX cadence (airtime-limited). Re-runs the e2e gate.

## Physical tasks (Frank — not CC)

- [x] **Overnight/no-network cold boot — CLOSED 2026-07-27** (`feat/rtc-boot-restore`, Option B).
      _Diagnosis (2026-07-13 boot, WITH Wi-Fi):_ at boot the kernel set the clock from the Pi 5's
      `rtc0` → **1970** (no/dead coin cell), then `systemd-timesyncd` restored its **saved-clock
      floor = last shutdown (Jul 08 21:51)**, and **nothing read the PiSugar RTC into the system
      clock.** apogee-ingest's `year ≥ 2024` gate passed on that stale floor and opened a
      **mis-dated session** (`session-20260709T015114Z`, really Jul 13); only **NTP** (15:40:10)
      corrected it — offline it would have been silently wrong.
      _Verification (2026-07-27, true Wi-Fi-OFF cold boot, **no network at boot** — Ethernet
      physically unplugged until +15 min so no NTP could sneak in):_ **PASS.** The floor bug
      reproduced exactly — the system came up at the timesyncd floor (`sys_before` = `14:53:50Z`,
      ~62 min stale); `apogee-rtc-restore` read the PiSugar RTC (`11:56:09-04:00`) and `decide()`
      returned **`action=set / reason=sys-behind-rtc`** (Δ ≈ 3739 s ≫ 120 s `_FORWARD_THRESHOLD_S`),
      stepped the clock, and dropped `/run/apogee-rtc-restored` — **before** `apogee-ingest` started
      (`11:56:09` vs `11:56:16`). Ingest's fail-closed gate then passed **on the marker, not NTP**
      (first NTP sync was `12:11:13`, ~15 min later when the cable went in — it postdates both the
      clock-set and the session-open, proving the link was dead at boot) and opened a
      **correctly-named session** `session-20260727T155616Z-8059ca.jsonl`.
      _Criterion (1) — PiSugar RTC hold — satisfied free by the hiatus:_ the RTC kept correct
      wall-clock across a **~13-day fully-powered-off** span at 69 % with no drain (read back
      `2026-07-27T10:45:47-04:00` on power-up); the 30-min hold test need not be re-run.
- [ ] **2.2 hotspot field test** — away from home Wi-Fi, confirm fallback to the iPhone hotspot.
- [x] **Live shake test — done 2026-07-08** (see first flight below); hand-*jerk* peaked 2.2 g
      (missed the 1 Hz sample), a sustained **circular swing** hit 6.4 g and tripped it.

## First flight — `2026-07-08-F1` (shake test, bench)

The full live cycle is proven end-to-end on real RF: **pad→ascent→descent→close**, dashboard
badge/T+/AGL, OLED ascent page, and the AGL **baseline reset on `flight_close`** all fired.
Index entry: **dur 87.6 s, 75 rx, 1 lost** (one real SEQ gap mid-swing), peak −74 ft raw,
**AGL baseline −84 ft (n 15)** → peak **10 ft AGL**, RSSI −38..−14. **Derivation round-trip
byte-identical** (rebuilt twice → same index; the annotation survives). Captured as a
**version-controlled golden fixture** — `ground/flights/tests/fixtures/f1_{session,ops}.jsonl`
(widened to include the 19 quiet pre-boost pad packets so the baseline recomputes) +
`test_f1_golden.py` asserts decode→segment→derive reproduces F1 exactly (incl. baseline), so
real over-the-air bytes now guard every future contract change. (Profile is bench noise — a
swing, not a climb; the 10 ft "peak" is sensor noise. A real *trajectory* awaits an actual flight.)

## Immediate next steps

1. **4.5 web publish** (`feat/flight-publish`) — **IN PROGRESS, data-driven model.** `flights
   publish` ships **DATA ONLY** into the portfolio site (a `flights.json` summary + per-flight
   CSVs under `projects/lora-flights/`) — never a `.qmd`. Stage-1 generator done in
   `ground/publish/` (pure, 8 tests): `flights_summary`, `permalink`
   (`…/projects/lora-flights.html?flight=<id>`), `write_flight_data`. The archive page is a
   hand-polished **Stage-2** artifact authored once in the site repo: `projects/lora-flights.qmd`
   — matplotlib/seaborn hero charts (`jupyter: lora-rocket-telemetry`, **`freeze:false`** so CI
   re-executes on data pushes) + **OJS** value boxes / selector / `?flight=` deep links. **Site
   env:** a uv `.venv` + registered `lora-rocket-telemetry` kernel in *this* repo (per the
   Portfolio Workflow doc); the site's action gets **one authorized line** registering that
   kernel in CI (no dep additions — CI already has pandas/numpy/matplotlib/seaborn). Mock built
   with F1's real data on pages-repo branch `feat/flights-section` (committed, **not merged** —
   Frank reviews + merges + pushes; then **Stage-3 tag** `v1.0-portfolio-genesis`). Local preview:
   `QUARTO_PYTHON=$(pwd)/.venv/bin/python3 quarto preview projects/lora-flights.qmd`.
2. **Assign the 6 panel-LED functions** (from decoded packets). *(Physical field/boot
   tests are under "Physical tasks" above.)*

## Backlog (not now)

- **`feat/oled-reinit-recovery`** — luma sends the SSD1306 init sequence **only at service
  startup**, then only pushes framebuffer bytes. A power-cycled OLED (connector reseats in
  transit) resets to display-OFF/charge-pump-OFF but **still ACKs on the bus**, so luma keeps
  writing pixels to a dark panel — **the OLED blanks for the whole launch, silently, no error
  anywhere** (found 2026-07-30: a rewire mid-run blanked it; only a physical restart re-inited
  it). Cheap self-heals: (a) **periodic re-init** (re-send the init sequence every N seconds —
  dead simple, always recovers, costs a few I²C writes); (b) **re-init on I²C error** (only
  fires on a *detected* fault — but a reset SSD1306 throws no write error, so this misses this
  exact case); (c) a **display heartbeat** (read back a register / detect blanking, re-init on
  mismatch — most correct, most code). **Recommend (a)** — a low-frequency unconditional re-init
  is the smallest change that actually covers the silent-blank case (b) can't see. **Same class
  of bug for the Epic 8 handheld OLED** — replicate the fix there.
- **Unit-install drift guard** (before Epic 8 replicates this config) — three systemd units
  (`apogee-ingest`, `apogee-rtc-restore`, `apogee-attest`) are **versioned in `ground/ingest/`
  but execute from `/etc/systemd/system/`**, with a hand-recreate step on SD rebuild. Same
  "right in the docs, wrong on the machine, found under stress" failure class the escape-hatch
  cwd bug was. Cheap fix: either a **verify-installed-units-match-repo check** (diff installed
  `apogee-*.service` against the repo copies; run at deploy/boot or as a test) **or** a single
  sanctioned `install-units.sh` (copy + `daemon-reload`). Not implemented — pick one when Epic 8
  needs it.
- **Stale-branch cleanup pass** — the repo carries ~24 merged/dead local branches (`feat/*`
  from Epics 1–4 already in `main`, plus `worktree-agent-*` merge-artifact branches). Prune the
  ones fully contained in `main` so `git branch` reflects only live work. Not urgent; do a sweep
  when convenient. (Don't delete anything not merged — verify `git branch --merged main` first.)
- **Pi 5 RTC coin cell (Option A)** — connect a battery to the Pi 5 RTC header (J5) so `rtc0`
  keeps time and the kernel sets a correct clock at boot with no PiSugar/NTP. Cleanest, most
  robust fallback; complements (doesn't replace) the `feat/rtc-boot-restore` software path. Frank
  to order the cell. **Epic 8 rider:** the handheld (Pi Zero 2 W) has **no `rtc0` at all**, so the
  software RTC-boot-restore (Option B) is the *only* option there — replicate it to the handheld.
- **Manual flight-open/close from the live dashboard (a "log" button)** — mark flight boundaries
  at the range when the 1 Hz launch detect misses. **Not a quick add** — the dashboard is a
  read-only consumer and the ops journal is one-writer (CLI). Invariant-respecting design: a POST
  endpoint on the ingest service force-opens/closes in the **live segmenter** and writes the
  advisory to the **session log** (service-owned → one-writer preserved), thread-safe so it never
  blocks RX. Live dashboard only (the public archive is static). Its own branch/epic.
- **"KC3ZTQ RadioRocket V2" portfolio writeup** — full Stage-2 page in the site repo when the
  project wraps (or at first real flight). Raw material already in-repo: [ADR 0001](adr/0001-packet-format-v1.md)/
  [0002](adr/0002-ground-rx-driver-spidev.md), [agl-baseline-v2-audit](agl-baseline-v2-audit.md),
  [telemetry-dictionary](telemetry-dictionary.md), the Portfolio Workflow doc, this RESUME history,
  and the genesis-flight story. Links the flight-archive page as the live exhibit. **Start
  `references.bib` accumulating now** (per the workflow doc): N3VEM RadioRocket attribution,
  LoRa / Part-97 sources, BMP390 / ADXL375 / 9-DoF datasheets as consulted.

## Notes / gotchas

- **Bench-artifact sessions:** session logs produced by bench tests (not flights) are registered
  in [`docs/bench-sessions.md`](bench-sessions.md) — the canonical, append-only provenance list so
  they aren't mistaken for real telemetry. Add a row per bench session; don't restate elsewhere.
- **Wake-on-charge = rising-edge, not presence:** `auto_power_on: true` (PiSugar, Epic 2.6's
  complement) boots the box when power is **(re)connected**, not when power is merely present —
  so `poweroff` with the charger plugged **stays off**, and **unplug→replug wakes it** (both
  verified 2026-07-27). If it wakes unexpectedly, suspect a power reconnect, not a timer. Setup +
  semantics: [`ground-station-wiring.md`](ground-station-wiring.md).
- **Real-RF golden fixture:** `ground/flights/tests/fixtures/f1_*.jsonl` is the F1 shake-test
  slice; `test_f1_golden.py` guards decode→segment→derive against real bytes. **Treat it like the
  ADR golden vector** — a change that alters F1's decoded fields or index entry is a contract break.
- **Launch detect samples at 1 Hz** (TX-coupled; `firmware/src/main.cpp` reads the ADXL once per
  `delay(1000)` loop, no FIFO/ISR). Bench hand-*jerks* fall between samples — use a **sustained
  circular swing** (>3 g held across a sample) to trip launch on the bench. See Epic 6 rider #6.
- **Standing merge gate:** the e2e check (sled TX → `ground/rx/` driver → payload matches
  the ADR fixtures) caught the newlib-nano float-printf bug that host tests could NOT —
  **keep the e2e check as a required gate for anything touching encode/decode.**
- **Session-file retention** is unbounded today (one JSONL per service start in
  `~/apogee-data/`; names are collision-proof). Fine for now — revisit rotation/pruning
  only if the ground station ever runs unattended for weeks.
- **Diagnostics:** repo carries a `pyrightconfig.json` so `ground.*` imports resolve;
  `pyright ground/` is clean (Pi-only libs + test union-access are suppressed with reasons).
- **newlib-nano `%f`:** float printf is off by default → the feather env carries
  `-Wl,-u,_printf_float` (float tags encode empty on-target otherwise, though host tests pass).
- **Feather M0 re-flashing:** first upload of a session works; re-flashes reliably need a
  **manual double-tap to bootloader** (SAM-BA flake). See memory `feather-m0-flash-double-tap`.
- **Ground data on the Pi** (not in repo): session logs `~/apogee-data/session-*.jsonl`
  (service-written) + `flights-snapshot.json` (disposable derivation cache). The old
  `rx_test.py` / `rx_driver_check.py` scratch scripts were deleted in the 4.2 branch.
- **One radio owner:** `apogee-ingest.service` owns SPI continuously — stop it
  (`sudo systemctl stop apogee-ingest`) before any direct radio work; never a second owner.
- **Service runs from `~/gs-venv`:** `ExecStart` points at `~/gs-venv/bin/python` (the OLED
  needs `luma.oled`, which system `python3` lacks). An **SD-card rebuild must recreate
  `~/gs-venv` with `--system-site-packages`** and pip-install `luma.oled` (`flask`/`spidev`/
  `lgpio` come through system-site). If the venv is missing the unit fails to start —
  system `python3` is no longer a drop-in substitute.
