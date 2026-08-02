# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: **2026-07-31** (Claude, on Mac + Pi 5). **This session: `feat/panel-leds` MERGED and
pushed** — the six-LED supervisor is live and enabled for boot on `apogee-gs`. Also landed three
pieces of process that outlive the branch: the **sanctioned deploy path**, the canonical
**"designed but INERT"** register, and **"cite, don't restate"**. Repo-wide **branch cleanup**
done (34 stale branches removed; Mac/GitHub/Pi all on `main` only). **4.5 is UNGATED** — F1 bench
data is sufficient to publish; see Immediate next steps. Earlier: RTC-boot-restore
merged + pushed (ADR 0003); **wake-on-charge** (`auto_power_on`) enabled; **graceful button
off-switch** validated (USB-C double-tap → clean `service_stop`; both PiSugar buttons close the log
cleanly); **OLED rewire verified** (the "dark" was a no-idle-page firmware gap, not hardware).
**`feat/panel-leds` is now BUILT, not merely designed** (2026-07-31): pure LED policy + supervisor
logic + lamp-sweep plan, the ingest heartbeat publisher, and the Pi supervisor shell/unit — see
"Open branches". Still designed-not-built: `feat/oled-heartbeat` layout redesign — see Backlog. Still parked from 2026-07-08: the flights page mock on pages-repo branch
`feat/flights-section` awaiting Frank's review→merge→push, then Claude tags `v1.0-portfolio-genesis`._

## NEXT SESSION — start here

**Next branch: `feat/oled-heartbeat` — THREE admitted items, ONE branch.** Do not start it in a
session that can't finish RED.
1. **Periodic redraw** so the display doesn't go dark when the sled is quiet (the defect hit on
   the bench 2026-07-30 — `_oled_update` renders only on an observation callback, so a quiet pad
   sits at luma's cleared-black init state and looks dead).
2. **Idle/quiet page with real content** — ready, waiting for `SRC:1`, clock provenance,
   RSSI `--`, liveness indicator.
3. **Render OFF the RX thread** (severity HIGH) — today a wedged I²C bus blocks packet handling,
   so a *display* fault can stop *telemetry capture*. RX loop publishes a view-model snapshot;
   a render thread consumes it.

**TDD the pure part** (state → rendered content); keep timer + threading glue thin, like
`ground/panel/`. Plan first, then RED.

**EXPLICITLY DEFERRED — do NOT build** (this is the redesign, not the fix): 28 px hero digits,
hand-drawn digits, committed bitmap font, golden-image tests, the three-page system, page
transitions/persistence, RSSI sparkline, burn-in mitigation, stale-hero treatment.

**After the OLED fix: Epic 6 (relay deployment)** — safety-critical, gets the slot while
attention is fresh. Epic 6 **before** Epic 7 (separation at main requires deployment to work).

### Architecture question to ANSWER next session (not now): Quarto render source of truth

**The mental model was wrong, so rebuild from this.** Frank had been carrying: *the page is built
in the telemetry repo and copied to the site repo for CI to publish.* **What is actually built:**
`projects/lora-flights.qmd` lives in the **site repo** (`~/velezf.github.io`), and CI
**re-executes the Python on every push** (`freeze: false`) — with **unpinned**
`pandas numpy matplotlib seaborn` resolving *latest at run time* on **Ubuntu / Python 3.11**,
while Frank develops on **macOS / pandas 3.0.3**. The telemetry repo ships **DATA ONLY**
(`flights.json` + per-flight CSV) via Stage-1 `flights publish`; it never writes `.qmd`.

**The fork to decide:**
- **Keep `freeze: false`** — CI is the render source of truth and auto-rebuilds on every data
  push; but the render env drifts from Frank's (unpinned deps, different OS/Python), and
  `_freeze/` must stay gitignored (guard added 2026-08-01: `_freeze/projects/lora-flights/`).
- **Switch to `freeze: true` with committed `_freeze/`** — Frank renders locally with the real
  telemetry venv (one env, reproducible, matches what he tests against) and CI needs no Python,
  no kernel, no deps at all; but figures only update **when he remembers to re-render**, and
  **stale output becomes possible again** — the exact failure this session was designed to
  prevent.

**Scope of the decision — it governs ONLY the two matplotlib charts.** The OJS half (value boxes,
selector, summary line, the three Plot traces) reads `flights.json` and the CSV **client-side at
page load** and is **never frozen either way**. That asymmetry is also why a stale-figure failure
is invisible on the page: the OJS numbers stay correct while the Python figures go stale — which
is exactly how preview output got mistaken for CI evidence on 2026-08-01.

### Where the tag lives: `v1.0-portfolio-genesis` is on THIS repo, not the site repo

**`v1.0-portfolio-genesis` tags `lora-rocket-telemetry` at `42eacb5`.** It was briefly placed on
`velezf.github.io` on 2026-08-01 and **moved** (deleted local + remote, re-tagged here) the same
day. **The tag marks a state of the SYSTEM that produced the data** — firmware, packet contract,
RX driver, ground service, storage model, hardening, panel — **not a state of a website**. The
site repo is a *publishing surface*; it carries no tags. Do not re-tag it.

### Follow-up decided 2026-08-01: PIN the CI deps (not `freeze: true`)

**This — not the freeze fork — is the real answer to the blast-radius risk.** Verified facts:
`publish.yml` runs a **full-site `quarto render`** on a **daily cron (`0 6 * * *`)** as well as on
push; `_quarto.yml` sets no `error: true`, so **one page failing to execute aborts the whole
render** and the gh-pages deploy step is skipped — **no project deploys**. With
`pip install … pandas numpy matplotlib seaborn` **unpinned**, an upstream release can fail the
site on a day nobody touched anything.

**Proposed change** — pin that one line:
`pip install jupyter nbformat pandas==3.0.3 numpy==2.5.1 matplotlib==3.11.0 seaborn==0.13.2 requests`

**⚠ SHARED-FILE CAVEAT — the reason this needs its own review.** `publish.yml` is shared:
`el-nino-watch-2026` **also** runs `freeze: false` with its own kernel and **has been rendering
against `latest` for months**. Pinning to Frank's local macOS versions silently changes what THAT
page renders against. **Do not fix one exposure by breaking someone else's working page.** The
proposal must state how we'd know el-nino still renders clean — render it locally against the
pinned set first, or pin and then watch the next 06:00 UTC cron before trusting it. Evidence
baseline: **30/30 recent runs succeeded**, and on the very run that published the flight archive
(`30714197232`, 2026-08-01) **`el-nino-watch-2026` rendered CLEAN — `Cell 1/8`..`8/8`** against
current `latest`. That is the pre-pin baseline: if el-nino breaks after pinning, the pin caused it.

**Why NOT `freeze: true` for `lora-flights`** (settled 2026-08-01): the two matplotlib charts are
the *cross-flight* ones whose whole job is to gain a point when a flight is published. Frozen,
they update only when someone remembers to re-render locally — and since the OJS half reads
`flights.json` **client-side and is never frozen**, forgetting once yields a page **internally
inconsistent with itself** (selector and value boxes show the new flight; the charts silently omit
it). That is worse than either stale-everything or fresh-everything, and far harder to notice.
Also relevant: the coupling is **pre-existing** (el-nino already carries it) and a failed render
does **not** take the live site down — gh-pages keeps serving the last good deploy.

**Rules that must survive the context break** — full text under "Working rules":
- **Admission rule:** admit only if it **(a)** prevents lost flight data, a corrupted record, or
  an ambiguous go/no-go at the pad, **AND (b)** has concrete evidence the failure is real.
- **Budget rule:** at most **one correctness branch + one hardening branch** open at a time.
- New ideas go to Backlog, not explored inline.

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
are collision-proof. **4.4 dashboard + 4.6 status OLED are merged and deployed** (4.6 for `SRC:1` on the bench —
three plan clauses deferred, see Epic status)
— live Flask/Chart.js dashboard (density pass: header callsign, per-SRC flight badge + live
age, T+, RSSI sparkline, events feed, health line) + SSD1306 status OLED on `0x3d`, both on a
per-SRC **AGL pad baseline** (ALT−baseline while `St:0`; raw ALT untouched in records; resets
on `flight_close`). Bench-verified on `apogee-gs` against live sled telemetry. **EPIC 4 IS CLOSED (2026-08-01)** — 4.5 published the flight archive on F1
alone and it is verified live.
Epic 8 groundwork merged. **`feat/panel-leds` merged 2026-07-31** — six-LED supervisor live and
enabled for boot.

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
  `git pull` works. **The deploy key is read-only and the Pi tracks `origin`, so an unpushed
  branch cannot reach the box by `git pull`** — that is exactly how the 2026-07-31 hand-copy
  drift happened. Deploy unpushed work over SSH from the Mac, never by copying files.
- **Wi-Fi:** home **WideRoad** (priority 0) first, **iPhone 17 hotspot** fallback
  (priority −10, infinite retry, persistent NM keyfile). Networking is netplan-rendered
  → NetworkManager. _(Hotspot secret lives only on the Pi, never in this repo.)_

## Deploying to `apogee-gs` — the sanctioned path

**Code reaches the Pi through git, never by copying files.** The absence of a written path is
what produced the 2026-07-31 hand-copy drift (a stale checkout running hand-placed files, whose
provenance had to be reconstructed afterwards by hashing). **Epic 8's handheld inherits this
procedure** — keep it in one place.

1. **Commit** on the feature branch (Mac). Frank's gate.
2. **Push the branch** to `origin` (Frank's gate — a *branch* push is separate from a `main`
   push). A WIP branch on the public repo is normal, disappears at merge, and gives durable
   off-laptop backup — the other lesson that keeps recurring.
3. **Pi pulls** with its existing read-only deploy key:
   `git fetch origin && git checkout <branch> && git pull --ff-only`.
   **`git status --porcelain` must be empty first** — a dirty tree means undeployed state that
   nobody can reproduce; inspect and discard it before checking out (`git diff` it first: on
   2026-07-31 the local edits turned out to be strictly *older* than the committed versions).
4. **Install units** from the repo — they execute from `/etc/systemd/system/`, not the checkout:
   `sudo install -m 644 ground/<area>/<unit>.service /etc/systemd/system/ && sudo systemctl daemon-reload`
5. **Restart** the affected services (`sudo systemctl restart apogee-ingest`;
   `sudo systemctl enable --now apogee-panel`).
6. **Verify — against the committed artifact, not by eye.** Confirm the installed unit matches
   the repo (`sha256sum` both), the service is `active`, and the *observable output* is correct
   (e.g. the heartbeat file's `ts` advancing ~1 Hz). Only then is a result attributable.

**Rejected alternative — the Pi as a git remote** (`git push apogee-gs <branch>` with
`receive.denyCurrentBranch=updateInstead` on the Pi). Rejected because it needs new machinery,
mutates the Pi's git config, and duplicates a read-only deploy key that already works — while
push-to-origin also buys off-laptop backup. **What we gave up is genuinely attractive, though:
`updateInstead` refuses to update a repo whose working tree is dirty**, which would have
*mechanically blocked* the exact drift we hit rather than merely documenting against it.
Revisit if pushing WIP branches to a public origin ever becomes undesirable.

## Host tests (the Mac) — `.venv-test`

Host tests run under **`.venv-test`** (gitignored): `.venv-test/bin/python -m pytest ground/ -q`.

**One venv, one purpose** — `.venv` is the Quarto/Stage-1 *render* env (its `pyproject.toml`
says so) and deliberately does **not** carry `pytest`; mixing them would repeat the
one-writer-per-file mistake in another form. Recreate with:

```
python3 -m venv .venv-test && .venv-test/bin/python -m pip install pytest pillow
```

**`pillow` added 2026-08-02** for the OLED drawing layer (`ground/oled/draw.py` renders a
128x64 1-bit image). Pinned to nothing, but the host and the Pi's `gs-venv` both currently carry
**12.3.0** — worth keeping aligned, since the redesign's golden-image tests will compare pixels
across the two machines.

**Rebuild implication:** a fresh Mac (or a wiped repo) has **no** pytest anywhere until this is
recreated — on 2026-07-31 pytest was absent from `.venv`, system `python3`, Homebrew, pyenv,
*and* the Pi's `~/gs-venv`, which blocked TDD outright until it was rebuilt. The ground suite is
pure/host-only, so it does **not** need the Pi. Current: **221 tests green**.

## Wired peripherals (bench-verified 2026-07-07)

| Device | Bus | Address / CS | Notes |
|--------|-----|--------------|-------|
| RFM96 LoRa radio | SPI0 | **CE1** (`/dev/spidev0.1`, pin 26); RESET GPIO25 (pin 22) | `RegVersion 0x12`. **Not CE0.** |
| OLED (Adafruit 938, SSD1306 128×64) | I²C-1 | `0x3d` | driven via `~/gs-venv` + **`luma.oled`** |
| PiSugar 3 Plus UPS | I²C-1 | `0x57` batt, `0x68` RTC | `pisugar-server`; auto-shutdown at 5% / 30 s |
| Front-panel LEDs ×6 | GPIO | physical **L→R: `16,12,26,13,6,5`** = 🔵🔵🔴🟢🟢🟢 (per-position, single-LED probed 2026-07-31) | active-high; bring-up via `ground/tools/led_check.py`. Canonical map: `ground/panel/leds.py` (host-tested) |
| Sled 9-DoF (bench, Epic 5.1) | I²C | LSM6DSOX `0x6a`, LIS3MDL `0x1c` | on the sled's STEMMA QT bus alongside BMP390 `0x77` / ADXL375 `0x53` |

**Native LoRa RX** = the repo's `ground/rx/` **SX127x driver** (raw `spidev`+`lgpio`,
host-tested against a fake SPI, CRC-enforcing, RadioHead-header aware). **Blinka rejected —
[ADR 0002](adr/0002-ground-rx-driver-spidev.md)** (RPi.GPIO won't run on BCM2712). OLED uses
`luma.oled`; the panel LEDs use **raw `lgpio`** (same single GPIO story as the RX transport —
no second GPIO abstraction on the box, which the Epic 8 handheld inherits) — the whole ground
stack is Blinka-free. `rocketman`
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
| 2 — Pi 5 ground-station bring-up | ✅ **CLOSED except 2.2 field verification.** (2.2's own acceptance clause is "verify cold-boot rejoin" and the hotspot field test is still open — calling the epic closed while its acceptance clause is unverified is the same claiming-coverage-we-lack pattern removed from the panel docs 2026-07-31.) **2.5 deviates from the plan BY DESIGN** — raw `spidev`+`lgpio`, not Blinka/`adafruit_rfm9x` (ADR 0002); plan text reconciled 2026-07-31. OS/SSH/Wi-Fi/Claude Code/deploy-key clone; radio SPI0/CE1, OLED 0x3d, PiSugar batt+RTC, **6 panel LEDs (per-position map probed 2026-07-31)**; **2.5 RX driver** (`ground/rx/`); **2.6 low-battery auto-shutdown** (+ wake-on-charge complement). **2.2 hotspot fallback field test** carried as the single open **physical validation** (deferred, not blocking — same pattern as the overnight cold-boot item; run post-merge, doubling as the marker-vs-NTP clock check); panel-LED *functions* → Epic 4. |
| 3 — Sled TX firmware + contract | ✅ **Complete.** ADR 0001 locked; encoder/launch/apogee/conversions as host-tested `lib/` units; `src/main.cpp` emits **ADR v1** (`V:1 SYS:7 SRC:1 …`) with live SYS/SRC/SEQ/St/MET (**B4/B5 folded into the integration commit**); **e2e verified** — sled→Pi driver, **22/22 ADR-OK**, 0 CRC errors. |
| 4 — Ground service (decode/log/dash/web/OLED) | ✅ **CLOSED 2026-08-01.** 4.1–4.5 done; 4.6 functionally done for `SRC:1` on the bench (three clauses deferred, below); 4.7 optional, not started. 4.1 decoder (`ground/decode/`); 4.2 **ingest** (`ground/ingest/` + `apogee-ingest.service` — radio owner → JSONL log + `LinkStats` + foreign-SYS/unknown-SRC + Part-97 callsign audit); 4.3 **flight logging** (`ground/flights/` — journal segmentation, multi-bird, export, CLI; index = f(session, ops)); **4.4 dashboard** (Flask + Chart.js, immutable snapshots, density pass) + **4.6 OLED** (`luma.oled` `0x3d`) on a per-SRC **AGL pad baseline**, both bench-verified live and **flown once** (`2026-07-08-F1`, real-RF golden fixture). **AGL baseline v2** merged: pure `pad_baseline()` (stability-gated trailing window) shared by live + derive — the zero **locks at flight_open**, unlocks at close, and `baseline_ft`+`baseline_n` are stored per flight in the index (auditable, reproduces on rebuild). Full ground suite **221 tests** (incl. `feat/rtc-boot-restore` + `feat/panel-leds`). **4.6 is NOT done as specified** (re-marked 2026-07-31): three plan clauses are deferred — **multi-node `SRC:2` display → Epic 7** (no lander exists), **"reuses the handheld's OLED rendering" → Epic 8** (no shared module exists), **"cut a window in the front panel" → enclosure** (still benchtop, not boxed). The clause that IS implemented — "driven straight off each decoded packet" — specifies the defect (render on the RX thread, no idle page) and was amended in the plan. **4.5 DONE 2026-08-01** — the archive is live at
`velezf.github.io/projects/lora-flights.html`, published on F1 alone and tagged
**`v1.0-portfolio-genesis` in THIS repo at `42eacb5`** (moved off the site repo 2026-08-01 —
see "Where the tag lives"). **Verified end to end, not merely built** — see the two-proof
method below. |
| 5 — 9-DoF integration | 🟡 **5.1 hardware evidence done** (LSM6DSOX 0x6a + LIS3MDL 0x1c on the sled bus; WHO_AM_I 0x6C/0x3D; sane gyro/mag). 5.2–5.4 not started; `Roll`/`Spin` reserved (ADR 0001 App. A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

**NONE OPEN.** `feat/panel-leds` **merged** (`--no-ff`, `6338aa9`) and pushed 2026-07-31 —
12 commits. **Branch cleanup done the same day: 34 stale branches deleted**, each verified an
ancestor of `origin/main` first; Mac, GitHub and Pi now carry **`main` only**. (Deleted tips
remain in the Mac reflog ~90 days, and every commit is in `main`'s history regardless.)

**Heartbeat verification — what was actually proven** (corrected 2026-07-31): the 1 Hz
loop-driven heartbeat was confirmed live on `apogee-gs`, and the running `service.py`,
`heartbeat.py` and the *installed* `apogee-ingest.service` were later verified **byte-identical
(sha256) to the committed versions** — so the result is sound and attributable. What was NOT
sound was reproducibility: the Pi's checkout was on `main`, 19 commits behind, with hand-copied
files and two superseded `ground/clock/` modules. Provenance verified after the fact by hashing,
not by the deploy path — which is why the **sanctioned deploy path** now exists. Re-verified
after the fact from a clean checkout: heartbeat ticking 1 Hz from committed code, all four units
hash-matching the repo, `apogee-panel` `active`/`enabled`, steady state confirmed on the physical
panel (`B_CLOCK` solid pos 2, `G_ALIVE` pulsing pos 6).

`feat/rtc-boot-restore` merged into `main` via `--no-ff` (RTC-boot-restore +
fail-closed clock gate + apogee-attest escape hatch; ADR 0003; verified on a Wi-Fi-OFF cold
boot) — **merged AND pushed** (`origin/main` carries it; the earlier "not yet pushed" note was
stale, corrected 2026-07-31 at the panel-LEDs merge).
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

1. ~~**4.5 web publish**~~ — **DONE 2026-08-01. EPIC 4 CLOSED.** Live at
   `velezf.github.io/projects/lora-flights.html`; tagged **`v1.0-portfolio-genesis`** in **THIS repo** at `42eacb5`. F1 annotated from the ops journal (`flights annotate` → `rebuild`, byte-identical).

   **THE TWO-PROOF PUBLISH METHOD — reuse this, don't re-derive it.** Two risks, orthogonal, each
   invisible to the other's test; neither substitutes for the other:
   - **Stale figures (`freeze`)** — invisible on the page, provable ONLY in the **Actions run log**:
     `Executing 'lora-flights.quarto_ipynb'` + `Cell N/M` under the *Render Quarto site* step.
     **LOCATION-PINNED:** `quarto preview` prints *character-identical* strings, so terminal output
     is NOT evidence — the log must come from a real run at
     `github.com/velezf/velezf.github.io/actions` triggered by a push to `main`. This exact
     confusion happened on 2026-08-01 and nearly shipped an unverified tag.
   - **Missing data files (`resources:`)** — invisible in the log, provable ONLY by `curl -sI`
     against the **`https://velezf.github.io/...`** URLs (not `localhost`). **Capture the 404
     baseline BEFORE deploying** so the 404→200 transition is itself proof.
   - **Then verify CONTENT, not just status:** a `200` proves a file exists, not that it is the
     right file. Fetch the served `flights.json` and confirm the annotation.
   - Why neither alone suffices: the **OJS half reads `flights.json` client-side and is never
     frozen**, so page numbers stay correct while Python figures go stale; and a CSV-only 404
     leaves value boxes populated over three empty charts.
2. **4.5 (historical detail — data-driven model).** `flights
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
   Frank reviews + merges + pushes; then **Stage-3 tag** `v1.0-portfolio-genesis`). **Local preview — run from the SITE repo** (`~/velezf.github.io`, where the `.qmd`
   lives), with an absolute path to *this* repo's render venv (verified 2026-08-01; the earlier
   `$(pwd)/.venv` form was wrong — it silently assumed both repos were one directory, and the site
   repo has no `.venv` at all):
   `QUARTO_PYTHON=~/code/lora-rocket-telemetry/.venv/bin/python3 quarto preview projects/lora-flights.qmd`
   **`QUARTO_PYTHON` is DISCOVERY-ONLY, not execution.** The page declares
   `jupyter: lora-rocket-telemetry`, so Quarto resolves a *kernelspec by name* and
   `~/Library/Jupyter/kernels/lora-rocket-telemetry/kernel.json` pins the interpreter as an
   **absolute path** into this repo's `.venv` — independent of cwd and of `QUARTO_PYTHON`. The env
   var only gives Quarto a Python that *has* `jupyter` so it can enumerate kernelspecs at all
   (the system Pythons are bare — the same gap that had no `pytest`).
   **A clean preview does NOT predict a clean Action run.** It shares kernel-resolution-by-name,
   cell execution, `freeze:false`, and n=1 chart survival — but it CANNOT test the CI
   `ipykernel install` step (locally the kernelspec already exists) or the gh-pages deploy.
   Necessary, not sufficient.
   **4.5 IS UNGATED (2026-07-31).** The old "gated on the first real flight" was never tested —
   the Stage-1 pipeline was run against F1 and emits a **complete, well-formed payload**:
   `peak_agl_ft 10`, `baseline_ft −84`/`baseline_n 15`, `duration_s 87.556`, `packets_rx 75`,
   `packets_lost 1`, `loss_pct 1.32`, `rssi −38…−14`, plus a 75-row CSV and a resolving
   `?flight=2026-07-08-F1` permalink. **Nothing breaks at n=1.** Two things are *thin* (the
   selector has one option; the AGL profile is a 10 ft blip then ~80 s flat at 1 ft) and one is
   **unverified** — the Stage-2 page lives in the *site* repo, so any cross-flight element
   (peak-over-time, flight count, personal best) needs an n=1 fallback or hiding until n≥2.
   Check that at review time; it is the only thing that could look *broken* rather than thin.
   **Two conditions:** (a) `flights annotate 2026-07-08-F1` first — `motor`/`field` are empty
   strings and would render blank; set them (`motor: none`, `field: bench`) so the honest
   labelling rides in the data, not in prose; (b) **do not dress up the 10 ft** — it is hand-swing
   sensor noise, not a climb. Presenting it as an achievement would be the
   claiming-coverage-we-lack pattern, in public.

   **Execution order:** annotate F1 → Stage-1 `flights publish` → Frank reviews/merges/pushes
   pages-repo `feat/flights-section` → add the one authorized kernel line to the site Action →
   verify CI re-executes (`freeze:false`) and the permalink resolves → local preview gate →
   tag `v1.0-portfolio-genesis`. **This closes Epic 4.**
2. **OLED branch — ONE branch, not three** (`feat/oled-heartbeat`): idle page + **render off the
   RX thread** + reinit recovery. Frank's stated next start after 4.5. See Backlog for detail.
3. **Panel LEDs — DONE and merged** 2026-07-31.

## Working rules (adopted 2026-07-31)

**Admission rule.** Admit work into the current scope only if it **(a)** prevents a failure that
loses flight data, corrupts the record, or misleads the operator at the pad, **AND (b)** has
concrete evidence the failure is real — an incident, a probe, or a signal that actively lies.
Clause (b) is what makes it a rule and not a mood: `feat/drift-guards` failed on (b) (three
historical incidents, two of which its mechanism could not catch) and was deferred; the LED map
passed on both and was built.

**Currently ADMITTED** (all small; the three OLED items collapse into one branch):
`write_ok` wiring (RED's disk-full leg is on the INERT register — it claims coverage it lacks) ·
OLED render off the RX thread (a display fault can stall capture) · OLED idle page (observed
2026-07-30) · battery-discharge logging (15% is unmeasured; if the pack is the non-Plus it is
~5 min of warning, not ~20).

**Budget rule.** **Two slots, evidence-gated** — at most one *correctness* branch and one
*hardening* branch open at a time. Anything admitted must name the failure it prevents and the
evidence for it. The backlog never enters the critical path on its own momentum; it waits for a
flight to produce evidence.

**Epic order: 6 before 7.** Epic 7's closure bar requires separation *at main*, which requires
deployment to work — building the lander first yields a payload with nothing to eject it. Epic 6
is also the only safety-critical epic and deserves the slot while attention is fresh; its 6.2
arm-pin state machine is pure host-tested logic, which this project does well.

**Epic 7 closure bar.** Done when, **in one real flight**: a `SRC:2` node transmits valid v1
packets that the ground service logs as a **separate flight record**; its transmissions **do not
collide** with `SRC:1` (measured, not assumed); it **survives boost-g** and impact; it
**separates at main and is recovered**; and its atmosphere fields appear on dashboard + OLED.
*Sequencing:* 7.3 forces the two deferred **Epic 6 firmware riders** (per-unit `-DSRC_ID`, ±10%
TX jitter) — they stop being optional the moment a second transmitter exists, so **admit them
into Epic 7, not Epic 6**. 7.6 also unblocks 4.6's deferred `SRC:2` clause. Cheapest first slice:
**7.1 + 7.2 + 7.3**, pure bench work on hardware already in hand, retiring multi-node risk before
any mechanical commitment.

## Backlog (not now)

- **`feat/oled-heartbeat`** — the OLED goes silently blank in two distinct ways, both fixed by
  **one periodic render loop** (redraw every 1–2 s instead of the current render-on-packet-only):
  1. **No idle page** — `_oled_update` (service.py) renders *only* on an observation callback, so
     with no sled transmitting the panel sits at luma's cleared-black init state = looks dead
     (found 2026-07-30: OLED "dark" was really *no content* on a quiet pad; raw white-fill + a
     luma text frame proved the whole HW/luma path good — genuine SSD1306, charge-pump lit it).
     Fix: a startup + periodic **idle/pad frame** ("apogee-gs ready / waiting SRC:1 / RSSI --").
  2. **Silent reset-blank** — luma sends the init sequence only at startup; a power-cycled OLED
     (connector reseats in transit) resets to display-OFF but **still ACKs**, so luma writes
     pixels to a dark panel, no error anywhere. Fix: the same loop **re-sends the init** each
     redraw (unconditional periodic re-init — covers the case an on-I²C-error check can't see,
     since a reset SSD1306 throws nothing).
  A periodic redraw-with-reinit is the single smallest change covering both. **Same bug class for
  the Epic 8 handheld OLED** — replicate there. (Merges the earlier `oled-reinit-recovery` +
  `oled-idle-page` notes — they converge on one heartbeat loop.)
  **Layout redesign is DESIGNED** (2026-07-30, design-only): number-dominant live page — 28px
  hero altitude AGL, inverted state band + ▲/▼ glyph, RSSI icon+dBm, thin full-width trend strip
  (combine, number wins on cramping); three pages (idle/live/summary) sharing a common header;
  pad-only diagnostics (baseline) live on the idle page only. **Fonts:** no TTF on the Pi and a
  system font breaks golden-image tests (host vs Pi diverge), so **hand-draw the hero digits**
  (~12 glyphs, bold, pure) + **commit one bold pixel TTF** to `ground/oled/fonts/` for small text.
  Render = pure `render(snapshot)->PIL.Image`, golden-image tested. Burn-in: **1 px frame-shift
  every ~30–60 s + dimmed idle contrast** (never blank — blank re-creates "dark looks broken").
  **Stale hero (lying-display — same class as the flight LED):** if packets stop mid-flight the
  altitude number **freezes and is visually identical to a live reading**. Needs a freshness
  treatment on the hero — invert/blink it and/or show a data-age ("2.4s") — gated by a
  **state-dependent** threshold: silence on the **PAD is normal** (no alarm), silence during
  **ASCENT/DESCENT is not** (alarm fast). Drive it off `last_rx_ts` age (same field the RX LED
  uses), threshold = f(flight state). Untreated, a frozen hero is the OLED twin of a lit
  flight-LED after an ingest crash.
  **Page selection & persistence:** page is chosen by **flight state, not a timer** — IDLE (no
  flight open), LIVE (a flight open, any SRC), SUMMARY (after `flight_close`). **SUMMARY holds
  until the next flight opens — NOT a timeout**: it is what the operator reads walking downrange
  with the box in hand; a timeout would blank the one number they went to fetch. Multi-SRC: LIVE
  shows the active SRC (or cycles). **If ingest restarts mid-flight:** derive the current page
  from the session/flight state at startup (recoverable), **not** in-memory-only flags — a restart
  must return to LIVE if a flight is still open, not drop the operator back to IDLE.
  **REQUIREMENT — render OFF the RX thread (severity: HIGH).** Today `_oled_update` renders
  *synchronously inside the RX loop*, so a wedged I²C bus (luma write hangs) **halts packet
  handling** — a ~$10 display fault can stop the box's only job, telemetry capture, and stall
  the heartbeat into RED. `feat/oled-heartbeat` MUST move rendering to its own thread (RX loop
  publishes a view-model snapshot; the render thread consumes it), so no display fault can ever
  block capture. This is a correctness requirement of the epic, not a nicety.
- **`feat/panel-leds`** — six front-panel LEDs (GPIO 5/6/13 green, 26 red, 12/16 blue) as an
  operator-glance surface. **Architecture LOCKED** (2026-07-30): a **supervisor** (`apogee-panel`
  systemd unit, independent of ingest) **owns all six GPIO lines**; ingest is only a *state
  source* — it publishes the heartbeat state file (**one writer**; the path is `STATE_PATH` in
  `ground/panel/heartbeat.py` — canonical there, deliberately not restated here). Fail-closed by default:
  no fresh ingest state → supervisor drives the "down" pattern. This is the fix for the
  lying-panel problem — an ingest crash mid-flight must not leave the flight LED lit; the
  supervisor (not ingest) owns it and clears it on stale heartbeat. **State file:** heartbeat
  `ts` written on a **1 Hz timer independent of traffic** (NOT event-driven — the exact
  `_oled_update` bug), with `last_rx_ts` a **separate** field; **stale threshold 3 s** (tolerate
  2 missed ticks, avoid flap); **atomic temp+rename**; parse-fail = retain last-good ts (age out,
  don't flip). **Assignment:** RED (supervisor) = NOT RECORDING (ingest down / gate refused /
  **write-failing — NOT YET WIRED**, see below), slow-pulse=shutdown, fast=low-batt.
  **Logical names bind to a physical POSITION** (left→right, 1–6) — never to a GPIO number and
  never to an ordinal like "the first blue", which is unresolvable standing at a real panel and
  is exactly what turned this into a bench question. Confirmed layout 🔵🔵🔴🟢🟢🟢:
  **pos 1** `B_RF` RF trouble (foreign=slow, CRC-climbing=fast) · **pos 2** `B_CLOCK` clock
  provenance (solid=RTC, blink=attested, off=unknown) · **pos 3** `RED` NOT RECORDING ·
  **pos 4** `G_FLIGHT` flight open (solid) · **pos 5** `G_RX` RX activity · **pos 6** `G_ALIVE`
  alive-heartbeat. RED and `B_CLOCK` are adjacent on purpose — both answer "is my data good?",
  so trust reads in one glance; `G_FLIGHT` sits on RED's other side as the recording-status
  pair. **Canonical map:** `LED_GPIO`/`COLOR`/`lamp_test_order()` in `ground/panel/leds.py`,
  host-tested for mutual agreement.
  **Blink vocab** off/slow/fast/solid + heartbeat; **power-on lamp test** sweeps all six (dead-LED
  detection + resolves the physical L→R order). **Pure `led_states(state)->{led:BlinkState}` core,
  host-tested** like the clock work; thin Pi-only GPIO shell. **Doc bug — FIXED 2026-07-31:** the
  wiring doc's LED order was reversed in *every row*; each line was lit individually on the
  bench and its position counted. Lesson recorded there: single-LED probing is the only reliable
  method — a running sweep is too fast to call, and a whole-panel glance invites the left/right
  slip that produced the original wrong map.

### Panel signals designed but INERT

**Canonical list — the ONE place that says which panel signals are wired end-to-end and which
are not.** Code cites this heading by name (`ground/panel/{leds,run_panel}.py`); anywhere else
that describes panel behaviour must link here rather than restate it. The hazard being managed:
a designed-but-inert safety signal is *worse than an absent one*, because the panel reads
"fine" while the condition it was meant to catch goes unshown. **Nothing may be described as
panel-covered until it comes off this list.**

| Signal | Designed behaviour | Why it is INERT today | To activate |
|---|---|---|---|
| **RED — write-failing leg** | RED SOLID when the session log stops persisting (disk-full, failed append) | The pure core honours `write_ok=False` (tested), but the ingest publisher **hardcodes `write_ok=True`** — the leg is unreachable end-to-end | Queue-backed writer exposes a health flag → `state_snapshot(write_ok=...)` |
| **B_CLOCK — attested case** | SLOW blink = operator-attested clock, distinct from SOLID = RTC-restored | The `/run` marker is an **empty touch file**, so the supervisor cannot tell restore from attest; `read_provenance()` can only return `rtc`/`unknown` and attested reads as RTC | `restore_clock`/`attest_clock` write the *reason* into the marker; supervisor reads it |

**Consequences to state plainly:** RED does **not** cover disk-full, and B_CLOCK does **not**
distinguish an attested clock from an RTC-restored one. Wire both before the panel is trusted
for go/no-go. Fuller rationale for each in the backlog entries below.

- **Writer health → `write_ok` (RED's write-failing leg is INERT — see the table above).** The pure
  LED core lights RED SOLID on `write_ok=False` (tested), but the ingest heartbeat publisher
  **hardcodes `write_ok=True`**. Fix: have the queue-backed writer expose a health flag (last
  append failed / queue overflowing) and feed it into `state_snapshot(write_ok=...)`. Wire this
  before relying on the panel for go/no-go.
- **Battery-low threshold — turn 15% into a MEASURED minutes-of-warning.** `LOW_BATT_PCT=15`
  is derived from an *assumed* ~5 W draw; the real draw (Pi 5 + radio + OLED + six LEDs) is not
  that number. The supervisor already polls `battery_pct` at ~1 Hz (once per `TICKS_PER_SEC`
  ticks, not every tick) — **log it over time to get the actual discharge curve for free**, then
  reset `LOW_BATT_PCT` from real minutes-to-5%.
  **Where it belongs:** the supervisor (`apogee-panel`) is its OWN process, so it may write its
  own output — but **NOT** a second writer to any of the three data files (session JSONL / ops
  journal / flights index; one-writer-each is locked). Log to **journald** (rate-limited — on a
  ≥1% change or ~1/min, never 8 Hz), the established audit channel (like the clock events): no new
  file, rotates, no SD wear, `journalctl -u apogee-panel` gives the curve. Also feeds a future
  **runway estimate** (“~18 min left”) on the OLED summary page. (Confirm the Plus 5000 mAh pack
  by eye first — see the `LOW_BATT_PCT` comment; 15% only holds for the Plus.)
- **Clock-provenance in the /run marker (B_CLOCK attested case — INERT, see the table above).**
  The supervisor can only tell clock-trusted (marker present) from unknown (absent); it can't
  distinguish RTC-restore from a manual attest, so B_CLOCK shows solid=RTC even when attested.
  Fix: have `restore_clock`/
  `attest_clock` write the reason INTO the marker (they touch it empty today) so `B_CLOCK` (pos 2) can blink
  on attest. Small follow-up to the clock module.
- **`feat/drift-guards` — NOT NOW, deliberately deferred (2026-07-31).** Would pair a
  non-duplication test with the unit-install guard below. **Deferred because the sanctioned
  deploy path removes most of the mechanism it would detect:** hand-copying happened because
  there was no sanctioned route to the Pi; once deploys go through `git pull`, the Pi cannot
  silently diverge. Building a detector for a failure mode we just designed out is backwards.
  **Re-evaluate after the deploy path has been used a few times** — if drift appears *despite*
  it, build then, against real evidence rather than three historical incidents.

  **Design, if it is ever built — INVERT the obvious approach.** The instinct is "assert docs
  agree with the authoritative constant". Better: **assert docs don't restate it at all.** You
  cannot detect a *wrong* path by searching for the *right* one — you'd have to shape-match
  (`/run/apogee[-/][\w-]*\.json`) and compare every hit, which brings regex maintenance and
  false positives on historical notes. Enforcing *non-duplication* needs no registry of expected
  values, has almost no false-positive surface, and is ~30 lines. Scope to **literal values
  only**; see the "cite, don't restate" convention in `CLAUDE.md` (adopted 2026-07-31, free).

  **Why the obvious version was worth less than it looked** — of the three incidents that
  motivated it, a path-drift test would have caught **one**:

  | Incident | Caught by a path-drift test? |
  |---|---|
  | Escape hatch restated across four locations | **No** — prose procedure, no literal to compare |
  | LED L→R order, `RESUME:63` vs `:270` | **No** — prose/emoji ordering, not a path |
  | State path wrong in `RESUME:257` + `heartbeat.py:3` | **Yes** |

  Two of three were prose, where the convention is the only workable tool. Recorded so this
  isn't re-derived.
- **The ops journal is the ONLY irreplaceable artifact in the system — it has no backup.**
  Everything else regenerates: sessions are raw capture, flights are derived, and the index
  rebuilds byte-identically from `derive(session, ops)`. **Annotations are human input and live in
  exactly one place — `~/apogee-data/ops-journal.jsonl` on an SD card.** Losing that card re-opens
  the very un-re-derivability gap closed on 2026-08-01 (the published `flights.json` carried
  annotations that no journal could reproduce). Distinct from the data-hop item below: that one is
  about workflow convenience, this one is about permanent loss of the only non-reproducible data
  in the project. Decide a backup/commit strategy.
- **Publish data hop — decide a home for the workflow.** The ops journal and sessions live on the
  Pi; the site repo lives on the Mac (`~/velezf.github.io`), so every `flights publish` needs a
  data transfer. Worked fine as a one-off on 2026-08-01, but decide where this workflow lives
  before the ad-hoc `scp` becomes habit.
- **CI kernel assertion (`jupyter kernelspec list | grep -q lora-rocket-telemetry`) — NOT NOW.**
  A missing kernel surfaces as a confusing *render* failure, not at the registration step that
  caused it; the one-line grep is an **assertion** (fails at the right place) rather than a
  **diagnostic** (dumps output nobody reads — and unread output stops being read even when it
  matters). Deliberately deferred: by the admission rule it fails clause (a) — it prevents a
  confusing debug session, not lost flight data. **Trigger to build it: the kernel step proving
  flaky across runs.** Recorded so the probe-vs-assertion reasoning isn't re-derived.
- **OLED redesign — three design gaps to close BEFORE building (raised 2026-08-02).** None are
  in the fix branch; all three are item-3 design decisions.
  1. **Digit overflow on the hero.** A 28 px hero fits ~4 digits. An L1 flight above **9,999 ft
     has no defined behaviour** — shrink the font, switch to `10.2k`, or clip? That is precisely
     the flight where the display most needs to work. Note the overflow policy belongs in the
     PURE layer (`_hero()` in `ground/oled/spec.py`), where it is testable; the drawing layer
     only picks a font size.
  2. **Trend-strip window — sample-based or time-based?** At 1 Hz, ~60 samples is the last
     minute: fine up to apogee, but **flat for the whole descent under chute**, when the strip
     would show nothing useful for minutes.
  3. **Hero freshness (the highest-consequence remaining lie).** If packets stop mid-flight the
     hero **freezes and is visually identical to a live reading** — the same lying-display class
     removed from the LEDs (a lit flight LED after an ingest crash). Needs a freshness treatment
     driven off `last_rx_ts` age with a **state-dependent** threshold: silence on the PAD is
     normal, silence during ASCENT/DESCENT is not.
- **OLED multi-SRC page cycling.** The LIVE page currently shows ONE panel, chosen by a rule
  that is **forced, not chosen**: with rendering moved off the RX thread there is no observed
  packet whose SRC keys the display, so `_pick()` prefers a panel with `flight_open`, else the
  lowest SRC. Cycling between multiple SRCs (rocket + lander) is a redesign idea and waits for
  Epic 7 to make a second node exist.
- **Consolidate the `/run/apogee-rtc-restored` marker path — FOUR restatements, own review.**
  The clock-trust marker is written out as a literal in `ground/panel/run_panel.py`,
  `ground/clock/gate.py`, `ground/clock/restore_clock.py` and `ground/clock/attest_clock.py` — a
  live **cite-don't-restate** violation of exactly the kind the convention was adopted for
  (2026-08-01). `ground/ingest/service.py` deliberately did NOT add a fifth: it imports
  `MARKER` from `ground.clock.gate` (2026-08-02). **Consolidating the other four touches the
  FAIL-CLOSED CLOCK GATE, so it gets its own branch and its own review — do not fold it into an
  unrelated branch.** Pick one owner (`gate.py` reads it, `restore_clock`/`attest_clock` write
  it) and import everywhere else.
- **Two pre-existing pyright errors (introduced with `feat/panel-leds`, unnoticed).**
  `ground/panel/tests/test_heartbeat.py:11` — `pytest` unresolved, because pyright runs against
  an interpreter without it (`.venv-test` isn't in `pyrightconfig.json`); and
  `ground/panel/tests/test_supervisor.py:94` — `None` passed to a `float` parameter. Verified
  present on clean `main`. The repo used to report **pyright 0**, so this is drift: pyright is
  not part of any gate, and nothing ran it on that branch. Fix both, and consider adding
  `venvPath`/`venv` to `pyrightconfig.json` so the pytest import resolves.
- **Unit-install drift guard** (before Epic 8 replicates this config) — three systemd units
  (`apogee-ingest`, `apogee-rtc-restore`, `apogee-attest`) are **versioned in `ground/ingest/`
  but execute from `/etc/systemd/system/`**, with a hand-recreate step on SD rebuild. Same
  "right in the docs, wrong on the machine, found under stress" failure class the escape-hatch
  cwd bug was. Cheap fix: either a **verify-installed-units-match-repo check** (diff installed
  `apogee-*.service` against the repo copies; run at deploy/boot or as a test) **or** a single
  sanctioned `install-units.sh` (copy + `daemon-reload`). Not implemented — pick one when Epic 8
  needs it.
- ~~**Stale-branch cleanup pass**~~ — **DONE 2026-07-31.** 34 branches deleted (26 `feat/*`+`docs/*`,
  7 `worktree-agent-*`, plus `origin/feat/gs-bringup` and the Pi's local `feat/panel-leds`). Each
  was verified an ancestor of `origin/main` *before* deletion, then deleted with `git branch -d`
  (the safe form) — two independent checks; 0 skipped, 0 refused. Worktree registry pruned first,
  since a branch checked out in a stale worktree cannot be deleted. Mac, GitHub and Pi now carry
  **`main` only**.
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

- **The data store on `apogee-gs` (`~/apogee-data/`) — four files, four owners.** `session-*.jsonl`
  ← the ingest service (raw capture). **`ops-journal.jsonl` ← the flights CLI** (human annotations;
  created 2026-08-01). `flights.json` ← **derivation only** — it is `rebuild` = `derive(session, ops)`
  and is rewritten wholesale, never edited (verified byte-identical across repeated rebuilds).
  **`flights-snapshot.json` ← the INGEST SERVICE** (`LiveFlights`), an advisory live snapshot —
  **do NOT hand-edit it and do not mistake it for the index**: as of 2026-08-01 it is stale
  (`duration_s 88.283`, no baseline fields — it predates AGL baseline v2), so publishing from it
  would ship wrong numbers.
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
