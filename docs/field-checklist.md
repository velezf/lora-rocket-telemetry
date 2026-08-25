# Field checklist — launch day

Phone-readable. Cold hands. No laptop. **Save this page offline before leaving.**

**One rule above all: WHEN THE LED PANEL AND THE OLED DISAGREE, BELIEVE THE LEDS.**

> Derived operational copy. Authorities, if anything here reads wrong later:
> `ground/panel/leds.py` + `ground/panel/supervisor.py` (LED semantics, thresholds),
> `ground/oled/spec.py` (screen), ADR 0003 (clock gate + escape hatch),
> `docs/ground-station-wiring.md` (panel positions).

---

## 1. Pre-departure — at home, with tools

- [ ] **PiSugar charged to full.** Auto-shutdown fires at **5 %**; RED fast-blink at **15 %**.
- [ ] **Sled LiPo charged.** Spare packed.
- [ ] **Sync the PiSugar RTC while the Pi clock is NTP-correct** — this is the single best
      pre-empt for a field morning with no network:
      `printf 'rtc_pi2rtc\n' | nc -q1 127.0.0.1 8423`
- [ ] **Both services survive a reboot:**
      `systemctl is-enabled apogee-ingest apogee-panel` → **`enabled` / `enabled`**
      `systemctl is-active  apogee-ingest apogee-panel` → **`active` / `active`**
- [ ] **Disk has room:** `df -h ~/apogee-data` — session JSONL grows ~1 record/s. Under 1 GB free, clean up.
- [ ] **Back up the ops journal off the SD:** `~/apogee-data/ops-journal.jsonl`. Only irreplaceable file in the system.
- [ ] **Join the Pi to the phone hotspot once, at home. Write its IP on tape on the box.**
      (`apogee-gs.local` usually resolves over the hotspot; the taped IP is the fallback.)
- [ ] **ONE SLED POWERED AT A TIME at the range.** Operational rule, not a protocol: the
      sleds have no coexistence design because they never fly together — one rocket flies,
      the other sled stays POWERED OFF. (Mixed-`SRC` traffic is a bench-only situation and
      is fine there.) The rule revives as engineering only when the lander (`SRC:2`) — the
      node designed to transmit concurrently — becomes real.
- [ ] **Antennas: the two ends have OPPOSITE rules. Know which is which.**
      **SLED — never power it without its antenna.** It transmits; an open port can kill the PA.
      **GROUND STATION — safe to power without one.** The Pi radio is **RX-only by
      architecture**, not by convention: `ground/rx/sx127x.py` defines only `SLEEP`/`STDBY`/
      `RXCONT` opmodes, TX mode (0x03) appears nowhere in `ground/`, no `send`/`transmit`
      function exists, and no PA/output-power register is ever written. Verified 2026-08-06.
      This is what allows bench work to continue while a pigtail is on order — the sled
      still needs its antenna at all times.
- [ ] Pi repo tree clean: `git status --porcelain` empty.

### Bring

- [ ] Ground box + antenna
- [ ] Sled + antenna + charged LiPo + spare
- [ ] **Phone** — hotspot, dashboard client, **and the time source for a clock attest**
- [ ] **USB-C cable** + charger/power bank
- [ ] Hex driver / tools for the sled bay
- [ ] Paper + pen (motor, field, notes → the ops journal later)
- [ ] This page, saved offline

---

## 2. Power-on order at the range

**Hotspot OFF for now** — that is what makes the clock check meaningful.

1. **Ground box on.** Watch the lamp sweep:
   all six LEDs light together (~1.5 s) → dark → a clean **left→right march**, twice.
   - Any LED that never lights is **dead**.
   - Any out-of-order jump means the wiring changed. Fix before flying.
2. **Wait ~30 s, then read the panel** (§3). Expect: **B_CLOCK solid, RED off, G_ALIVE pulsing 1/s, G_RX dark.**
   - **RED solid here → §4 before anything else.**
3. **OLED** should show `CLK rtc` on the pad page, with **no network up**. That is the marker-vs-NTP proof — note the time.
4. **Now turn the phone hotspot on** → §5.
5. **Sled: antenna first, then battery.** Hold it **still and level for ~5 s** — the baro zero is calibrated at boot.
6. Within seconds the box shows **G_RX fast-blinking** and the OLED starts showing altitude.
7. Place on the pad. **Leave it transmitting, undisturbed, for ≥30 s before launch** — the AGL zero locks
   from the last **15 seconds** of quiet pad data (trailing ~2 s excluded; TIME-based at any rate —
   authority `ground/flights/baseline.py`). Handling it during that window corrupts the zero.
   **Bonus while it sits: pad frames carry the raw 9-DoF channels — every quiet pad minute is free
   Epic 5 calibration data. Longer is better.**

---

## 3. THE GO/NO-GO READ

Panel, left → right (positions 1–6): 🔵 🔵 🔴 🟢 🟢 🟢

| # | LED | Healthy on the pad | Anything else |
|---|-----|--------------------|---------------|
| 1 | `B_RF` blue **(INERT — always dark, ignore)** | **dark** | **Not a live signal today. Ignore this LED.** |
| 2 | `B_CLOCK` blue | **solid** = clock trusted | dark = no clock marker → ingest will not start → §4 |
| 3 | `RED` | **off** = recording | any RED at all → §4 |
| 4 | `G_FLIGHT` green | dark until launch | solid = a flight is open |
| 5 | `G_RX` green | **fast blink** (4 Hz) while the sled transmits | dark = no accepted packet for **3 s** |
> ## THE GO/NO-GO IS `G_ALIVE` PULSING — NOT "NO RED LIGHTS"
>
> **A PRECEDENCE CHAIN MAKES LOWER-PRIORITY STATES MASKABLE.** RED is a SUMMARY signal, never
> a primary read: its order is `shutdown > low-battery > not-recording`, so **a fast or slow RED
> is busy saying something else while nothing is being recorded.**
>
> The go/no-go is **`G_ALIVE` (pos 6) PULSING** — the positive assertion that the RX loop is
> turning — with **RED off as confirmation, not as the check.**
>
> "No red lights" is what anyone would instinctively check, and it is wrong.

| 6 | `G_ALIVE` green | **one pulse per second** | solid or dark = **not healthy** — ingest or the supervisor is dead |

### **GO = pos 2 solid · pos 3 OFF · pos 5 blinking · pos 6 pulsing once per second.**
### **Anything else is NO-GO. Do not launch.**

`G_ALIVE` is never solid by design. Solid or dark means the panel has stopped telling the truth.

`G_RX` counts **accepted** packets only (our SYS, known SRC). A transmitting sled with a dark `G_RX`
means wrong network/source ID or no link — not "quiet".

### OLED on the pad

`SRC:1` · big altitude in **ft** · `RSSI <n> L<loss>%` · **`CLK rtc`** · spinner glyph changing every second.
(The callsign after `SRC:1` only appears once the sled beacons `CALL` — it does not today. Blank is normal.)

### **WHEN THE PANEL AND THE OLED DISAGREE, BELIEVE THE LEDS.**

The panel is supervisor-owned in its own process and survives the failures it reports.
The OLED render thread lives **inside** `apogee-ingest`; when that dies the screen **freezes on plausible
content and cannot report its own death**.

**Dark `G_RX` + a live-looking altitude on the OLED = ingest is dead and the display is showing you the past.**

---

## 4. RED — and the attest recovery

- **RED SOLID = NOT RECORDING.**
- **RED SLOW PULSE (1/s) = shutting down.**
- **RED FAST (4 Hz) = battery ≤ 15 %.**

**Precedence trap:** shutdown and low-battery **outrank** not-recording, so a fast or slow RED **hides**
whether you are recording. `G_ALIVE` is the tiebreaker: **pulsing = ingest alive; dark = not recording**,
whatever RED is doing.

**RED does NOT cover a full disk.** That leg is not wired. Check `df` before you leave (§1).

### RED solid + B_CLOCK solid

Clock is fine, ingest is not: `sudo systemctl restart apogee-ingest`, then `journalctl -u apogee-ingest -n 50`.
Do not fly until RED is off.

### RED solid + B_CLOCK dark → the clock gate refused

By design. The gate is **fail-closed** and there is no NTP at a field: a dead RTC means ingest refuses to
open a session, because a **mis-dated flight record is worse than none**.

Set the clock from your phone and vouch for it — three commands, run on the Pi:

```
sudo date -s '<YYYY-MM-DD HH:MM:SS>'    # set from a watch/phone
sudo systemctl start apogee-attest      # drops the trust marker (from the repo root, always)
sudo systemctl start apogee-ingest      # gate now passes on the marker
```

Break-glass only, if the unit is missing — **and it MUST run from the repo root**, else `ground.clock`
is not importable:

```
cd ~/lora-rocket-telemetry && ~/gs-venv/bin/python -m ground.clock.attest_clock
```

**Confirm within seconds: RED off · B_CLOCK solid · G_ALIVE pulsing.** Then re-read §3.
(B_CLOCK reads *solid* after an attest too — it cannot distinguish attested from RTC-restored.)

---

## 5. Hotspot check — closes 2.2, no laptop needed

> ### LID OFF. IT IS A WI-FI RULE AS WELL AS A THERMAL ONE.
> The Pi 5's built-in Wi-Fi is **inside the metal box** and **cannot take an external
> antenna** — unlike the LoRa radio, there is no connector for one. A closed lid shields it
> and the hotspot link dies, which looks exactly like "the dashboard is broken".
> **LID OFF = WI-FI WORKS.** It was already the thermal rule (open airflow over the passive
> heatsinks); it is now also the connectivity rule, and the same action satisfies both.
> If the box is ever sealed: vent holes **and** a USB Wi-Fi dongle with an external antenna.
>
> **Shielding is not the first thing to suspect at home.** Measured 2026-08-06 with
> everything mounted in the box: the home AP scanned at **signal 100**. If Wi-Fi is missing,
> check the two software switches FIRST — `nmcli radio wifi` (was `disabled`) and
> `rfkill list wifi` (was soft-blocked). Both were off, both persist once set, and neither
> is visible from "the Wi-Fi doesn't work".

**VALIDATED 2026-08-07 — everything below except cold-boot rejoin.** Router OFF, Ethernet
down, home Wi-Fi gone: the Pi ran on the hotspot alone and served the dashboard both ways —
`http://172.20.10.2:8080` HTTP 200 in 0.124 s, and `http://apogee-gs.local:8080` HTTP 200
(mDNS resolves over the hotspot, so the name is the durable answer and the taped IP is the
fallback, not the other way round). Sled reception continued throughout, 0 loss.
**TAPED IP: `172.20.10.2`** — a DHCP lease on a /28, so treat the name as primary.

### STANDARD SAVED-NETWORK VERIFICATION — run this on any Wi-Fi the box must join alone

A profile that `nmcli connection show` reports as healthy can still never connect
unattended. Four fields decide it, and three of them fail SILENTLY:

```
sudo nmcli -g connection.permissions,802-11-wireless-security.psk-flags,\
              connection.autoconnect,connection.timestamp \
     connection show "<profile>"
```

| field | required | why it fails silently otherwise |
|---|---|---|
| `connection.permissions` | **EMPTY** | non-empty = user-scoped: it connects only while THAT USER IS LOGGED IN. At boot nobody is. |
| `802-11-wireless-security.psk-flags` | **0** | 0 = password stored in the profile. 1 = "ask an agent" — and there is no agent at boot. |
| `connection.autoconnect` | **yes** | with `autoconnect-retries 0` for infinite retry |
| `connection.timestamp` | **NON-ZERO, and advancing** | **0 means it has never once associated.** Existence, priority and a plausible password all still read fine. |

**The timestamp is the only one of the four that can prove the profile has actually worked.**
The rest describe intent; the timestamp describes history.

**How we learned the profile had NEVER worked:** `nmcli -g connection.timestamp connection
show <profile>` returned **0**. The profile existed, autoconnected, was prioritised, and had
never once associated — every check short of the timestamp said it was fine. It now reads
`1786129162`. **Use the timestamp, not the profile's existence, as the evidence.**

**2.2 CLOSED 2026-08-07 on this evidence.** One edge is untested and named rather than
hidden: the association was forced with `nmcli connection up`, so unattended rejoin on a
cold boot has not been observed. Closed anyway, deliberately — **the hotspot is a
CONVENIENCE path, not a DATA path.** If it fails at the pad nothing is lost: ingest keeps
capturing, the panel LEDs keep reporting, the OLED keeps showing flight state. The dashboard
is the one surface whose absence costs nothing that matters, which is what makes the
remaining risk acceptable rather than merely unlikely.
**If the page does not load in the field, it is not a go/no-go input** — check `G_ALIVE`
and fly.

- [ ] Phone Personal Hotspot **ON**.
- [ ] Pi on the hotspot (it autoconnects; priority 50, infinite retry). First cold boot in
      the field doubles as the rejoin observation — **note the result, do not gate on it.**
- [ ] Phone browser → **`http://apogee-gs.local:8080`** (or the taped IP).
- [ ] **It loads → the Pi is on the hotspot.** The dashboard binds `0.0.0.0`; nothing else needed. **2.2 closed.**
- [ ] Note the time, and that the OLED already said **`CLK rtc`** *before* the hotspot came up (§2 step 3)
      — that is the marker-vs-NTP evidence.

**If the page does not load:** check `G_ALIVE` first.
Pulsing → it is the network, not ingest. Dark → ingest is down; §4, and the hotspot question is unanswered.

---

## 6. The flight opened

All three should agree:

- [ ] **`G_FLIGHT` (pos 4) SOLID**
- [ ] OLED flips to the **LIVE page** — altitude hero + `P <peak>ft`, no `CLK` line
- [ ] Dashboard badge reads **`IN FLIGHT`** and the counter becomes **`T+<n>s`**

The flight opens on the **sled's own** ascent report (3.0 g launch detect), not on a ground judgement.
If `G_FLIGHT` is dark after a clean boost, the boost packet was lost — recoverable later with `flights open`.

---

## 7. Post-flight — close out and recover the data

- [ ] Flight **closes automatically after 90 s of telemetry silence** — and **since the 10 Hz build
      the landed sled KEEPS BEACONING at 1 Hz** (`St:2`, battery-bounded), so that silence only
      arrives after you power the sled off at recovery. **Expect `G_FLIGHT` to stay solid until
      then; that is the new normal, not a stuck flight.** Order: recover → sled off → ~90 s → closed.
- [ ] To close it exactly (or sooner), use the CLI `close` below.
- [ ] **Do not yank power.** Shut down cleanly (PiSugar button / `sudo poweroff`); RED slow-pulses
      through shutdown — let it finish.
- [ ] **Write it down at the field:** flight number, motor, field name, anything odd. Paper or phone note.

Journal it (repo root on the Pi, `flights` = `python -m ground.flights.cli`):

```
cd ~/lora-rocket-telemetry
~/gs-venv/bin/python -m ground.flights.cli rebuild ~/apogee-data/session-<...>.jsonl \
    --ops ~/apogee-data/ops-journal.jsonl -o ~/apogee-data/flights.json
~/gs-venv/bin/python -m ground.flights.cli list ~/apogee-data/flights.json
~/gs-venv/bin/python -m ground.flights.cli annotate <flight-id> \
    --index ~/apogee-data/flights.json --ops ~/apogee-data/ops-journal.jsonl \
    --label '<name>' --motor '<motor>' --field '<field>'
~/gs-venv/bin/python -m ground.flights.cli rebuild ...   # re-derive so the index carries it
```

- [ ] **Back up `~/apogee-data/ops-journal.jsonl` the same day.**
      Sessions are raw capture and the index is derived — both regenerate. **Annotations are human input
      and live in exactly one place, on one SD card. It is the only irreplaceable artifact in the system.**

---

## 7b. F2 DELTAS — the 10 Hz build (first flown F2; read once before launch day)

Everything above still applies. What the 2026-08-25 builds changed at the field:

- **In flight the sled transmits at 10 Hz** (pad stays 1 Hz), for **5 minutes from liftoff**,
  then drops back to 1 Hz beaconing — that bound is why a landed sled can't drain itself at
  58.9 % duty in the grass. `St:1` appears ~0.5–1 s after liftoff (confirm-or-revert; MET is
  backdated, so T+ is not delayed). `St:2` latches at apogee and rides all the way down.
- **Frame shapes switch with `St`:** pad frames carry raw `Gyx..Mgz` (calibration record),
  flight frames carry `Wmx` (spin envelope). The dashboard/OLED need nothing from you.
- **The on-rail power-cycle (see PAD SEQUENCE) now does double duty:** the sled clears a
  stuck I2C bus at every boot and would report it — if the sled comes up dark after a power
  cycle (no `G_RX` recovery), cycle it again; that is the known wedge and its known recovery.
- **Dark `G_RX` while the sled is DEFINITELY transmitting has a third cause** besides wrong
  ID and no link: the ground radio's own wedge (it once decoded nothing for 3.7 h while
  ingest looked healthy). Recovery: `sudo systemctl restart apogee-ingest`. The automatic
  re-init hardening is NOT built — this manual step is the mitigation.
- **Write down RSSI vs distance while walking the sled out** (dashboard on the phone):
  field-range margin has never been measured, and F2 IS the measurement. Close-range
  baseline for reference: **−40 ±1 dBm** (post-pigtail bench geometry).
- **A 0 % loss figure cannot see sled-side TX degradation** (scheduling skips don't gap
  `SEQ` by design). If something feels wrong at 10 Hz, the tell is packet AGE/cadence on
  the dashboard, not the loss number.

## 8. What would make me lose the flight record — by LIKELIHOOD

1. **RED on the pad, and I launched anyway.** Ingest was stopped and never restarted — that has genuinely
   happened on this box. Nothing is recorded and the OLED still looks fine.
   → **Pre-empt: read §3 at the pad AND again 60 s before launch. RED off + G_ALIVE pulsing, or no launch.**
2. **Dead RTC, no NTP at the field.** The gate fails closed; ingest never starts; RED solid, B_CLOCK dark.
   → **Pre-empt: sync the PiSugar RTC before leaving (§1); phone gives the time; §4 is the recovery.**
3. **PiSugar flat.** RED fast at 15 %, hard shutdown at 5 %. The 15 % warning is unmeasured — treat it as
   minutes, not hours.
   → **Pre-empt: full charge before leaving; USB-C + power bank in the bag; on RED fast, recover the box.**
4. **The sled is not transmitting** — flat LiPo, loose antenna, or wrong SYS/SRC. Ground records nothing
   worth having and `G_RX` is dark.
   → **Pre-empt: G_RX fast-blinking before you walk away from the pad; check the battery volts on the dashboard.**
5. **SD full.** Capture stops and **the panel does not tell you** — RED's write-failing leg is not wired.
   → **Pre-empt: `df -h ~/apogee-data` before leaving; clear old sessions at home, never at the field.**

**And the one that is not a lost flight but a permanent one: losing the SD card with the ops journal.
Copy it off the same day.**

## Panel and OLED quirks that are NORMAL today — do not diagnose these

- **`SRC:1` with no callsign is NORMAL.** The sled emits no `CALL` tag; beaconing never landed.
  A blank callsign is not a fault.
- **Position 1 (`B_RF`) dark is NORMAL and PERMANENT.** It is inert end to end —
  `state_snapshot()` never publishes `crc_climbing` or `rf_foreign`, so the signal cannot fire.
- **`G_RX` is a continuous 4 Hz blink** while packets are inside the 3 s window (the sled sends
  at 1 Hz), not a per-packet flicker. It counts **ACCEPTED frames only** — traffic with the
  wrong `SYS`/`SRC` reads as **silence**, not as activity.
- **`B_CLOCK` solid means "clock trusted", NOT "RTC-restored".** An operator attest yields the
  same solid, and the OLED prints `CLK rtc` either way.

## PAD SEQUENCE — power-cycle the sled ON THE RAIL

Carrying the rocket out and loading it on the rail can latch `in_flight_` **before the motor
lights** — then you are on the pad with the sled sending `St:1`, a flight already open, and the
baseline window poisoned by handling.

**Order: rocket on rail → POWER-CYCLE THE SLED → wait ≥30 s undisturbed → confirm on the ground
→ arm → launch.**

**What confirms the power-cycle worked (check within ~2 s of it coming back):**

| Look for | Meaning |
|---|---|
| **`G_FLIGHT` (pos 4) DARK** | **no flight open — THIS is the check** |
| `G_RX` (pos 5) blinking | the sled came back and is transmitting |
| OLED state reads `PAD` | detector is cold |
| `SEQ` restarts from a low number | a reboot resets the counter — a jump backwards proves the cycle took |

**If `G_FLIGHT` is LIT, the power-cycle did NOT clear it.** Either it did not fully power down,
or handling re-latched it after boot. Cycle again. **Do not arm until position 4 is dark.**

**The ≥30 s undisturbed matters twice:** the AGL zero locks from a 15-second window with the
trailing ~2 s excluded (time-based — `ground/flights/baseline.py`), so handling during it poisons
the zero and **every altitude for the flight is silently offset.**
