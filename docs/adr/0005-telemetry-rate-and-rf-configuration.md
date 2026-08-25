# ADR 0005 — Telemetry rate and RF configuration: 10 Hz at SF7/BW500

**Status:** ACCEPTED — §8's gate was measured and passed 2026-08-06 (see §8). **Read
that as clearing the DECISION, not the build: the measurement was taken at 1 Hz
arrival / BW125 / 109 B frames** (§8's own caveat) — the artifact that flies is
covered only by A1.6's sustained-10 Hz bench, which is still pending.
**Date:** 2026-08-06
**Supersedes:** nothing. **Amends:** the RF configuration implied by ADR 0002's receiver.

## Context

The system transmits at 1 Hz. **A whole flight is roughly 20 seconds, so the entire
record is about 20 points** — enough to say a flight happened, not enough to plot it.

The target that drives this decision is an **OpenRocket-style plot**: altitude, vertical
velocity and vertical acceleration against time, with event markers. That is a
resolution requirement, and it is the first requirement this project has had that the
wire itself cannot satisfy. Naming it changes what "faster" has to mean: not "more
packets" but "enough points to draw a curve through".

The sled already SAMPLES at a measured 17.00 Hz (`RATE:` self-report). The data exists
on board. The constraint is entirely in getting it off.

## Decision

**Transmit at 10 Hz, full ASCII frames, SF7 / BW 500 kHz / CR 4:5, at 17 dBm.**

With the fields this plot needs (§4), the worst-case frame is **139 B**, which at
SF7/BW500 is **58.94 ms** of air time — **58.9 % duty at 10 Hz**, against a ceiling of
**16.97 pkt/s**.

## 1. Why the bandwidth is the knob

Three parameters set LoRa throughput. Two are already spent:

- **CR is already minimal at 4:5.** There is nothing to recover.
- **SF6 is rejected on mechanism, not margin.** SF6 requires *implicit-header,
  fixed-length* packets. The wire format is ADR 0001 — space-delimited `KEY:VALUE`
  ASCII, deliberately **variable length**, deliberately tolerant of missing and unknown
  tags. Implicit header fights that at the mechanism level: it would force every frame
  to a fixed size, which either pads every packet to the worst case (spending the air
  time SF6 was supposed to save) or freezes the field set (destroying the additive
  evolution ADR 0001's versioning policy is built on). **SF6 buys speed by removing the
  property that makes the format survivable.**
- **BW is therefore the knob**, and it is a clean one: doubling bandwidth halves symbol
  time and halves air time, with a known and payable sensitivity cost.

| | ToA (139 B) | ceiling | duty @10 Hz | sensitivity |
|---|---|---|---|---|
| BW 125 kHz (today) | 235.8 ms | 4.24 pkt/s | **236 % — impossible** | −123 dBm |
| BW 250 kHz | 117.9 ms | 8.48 pkt/s | **118 % — impossible** | −120 dBm |
| **BW 500 kHz** | **58.94 ms** | **16.97 pkt/s** | **58.9 %** | **−117 dBm** |

**At the current bandwidth the target is not merely expensive, it is unreachable** —
10 Hz needs 236 % of the available air time. The bandwidth change is not an
optimisation; it is the enabling condition.

## 2. Why the RF path can pay for it

Bandwidth costs sensitivity: −123 → −117 dBm, **6 dB**. This flight profile has it to
spend, and the reasons are specific rather than optimistic — mid/L2 flights, an
**elevated transmitter** with unobstructed line of sight, short duration, and a
quarter-wave on the ground.

Worst-case slant range taken as **1.5 km**:

```
FSPL = 32.44 + 20·log₁₀(434 MHz) + 20·log₁₀(1.5 km) = 88.71 dB
RX   = 17 dBm − 88.71 dB = −71.7 dBm   (0 dBi assumed both ends)
MARGIN vs −117 dBm sensitivity = 45.3 dB
```

> **CAVEAT RETIRED 2026-08-08 — repair CLEARED by Frank on the numbers below.** The
> receive path was re-validated end to end after the u.FL re-solder + bulkhead pigtail:
> close range (few ft, usual bench geometry) **−40 ±1 dBm, zero loss, σ = 0.38 over
> 45/45 packets** — 40 dB of the 42–66 dB antenna deficit recovered, **2 dB shy of the
> −38..−14 gate's weak edge**, attributed to the new chain's insertion loss (u.FL +
> pigtail + bulkhead) plus the antenna change. **Named, not hidden:** the mechanical
> wiggle test (joint under flex) was OFFERED AND WAIVED — a σ=0.38 feed is not a broken
> joint's signature, but joint robustness under field vibration rests on judgement, not
> measurement. The formal u.FL continuity meter check was likewise overtaken by the
> working link and never run. Field-RANGE margin (vs the ~42 dB design number below)
> remains unmeasured until a flight.
>
> *(Original caveat, kept for the record:)* **THIS MARGIN IS A DESIGN ASSUMPTION, NOT A MEASUREMENT.** It assumes 0 dBi at
> both ends and an intact RF path. At the time of writing the ground station's u.FL
> connector has been **re-soldered** and its bulkhead pigtail is **damaged, replacement on
> order** — so the receive path is unvalidated end to end. The number becomes evidence only
> when the RSSI comparison in §8 passes: close-range RSSI back in the **−38 to −14 dBm**
> bench band. Until then, **any weak-RSSI symptom is the connector until proven otherwise**,
> and the 6 dB this ADR spends on bandwidth is spent against an unverified budget.
>
> Recorded antenna-less baseline for that comparison: **−80/−81 dBm**, session
> `session-20260806T174610Z-4d657e` (1,724 packets). Against the bench band that puts the
> missing antenna at **42–66 dB**, which is the quantitative pass condition for the repair.

Subtract 2–3 dB for connectors and cable and call it **~42 dB of margin**. A tumbling
airframe produces deep nulls as the antenna sweeps through its pattern; 20–30 dB fades
are ordinary. **The margin absorbs a 30 dB fade with room left**, which is the number
that matters — not the clear-air link, which was never in doubt.

**TX power drops 23 → 17 dBm as part of this decision, not as a separate one.** At
58.9 % duty the transmitter is keyed more than half the time, so thermal load is the
binding concern; 6 dB off is the answer to that, and the link budget above already
assumes the reduced power. Two changes, one justification.

## 3. Band plan

500 kHz centred on 434.0 MHz occupies **433.75 – 434.25 MHz**, inside the US 70 cm
allocation (420–450 MHz). Amateur is **secondary** here under §97.303 — accept
interference from, and do not cause interference to, primary government radiolocation.
Operation is under **KC3ZTQ**; Part 97 imposes no duty-cycle limit, which is why duty
appears above as a thermal constraint and not a regulatory one.

The segment overlaps heavily-used 433 MHz ISM devices. That is a **noise-floor**
consideration, not a legality one, and it is a reason to keep margin rather than spend
all of it.

## 4. What the plot needs on the wire

Three fields, because the plot cannot be reconstructed from what is sent today:

- **`Vel` — onboard vertical velocity**, dh/dt computed at the sample rate with light
  smoothing. **Velocity differentiated on the ground from 10 Hz `ALT` would be noise**:
  differentiation amplifies quantisation, and the barometer's step is a meaningful
  fraction of the per-sample altitude change. Computed on board at ~22 Hz it is the real
  curve. This is the general principle — *derive where the data is dense, transmit the
  derivative* — and it is why a higher TX rate alone would not have produced this plot.
- **`Gmx` / `Gmn` — the G envelope across each TX window**, not an instantaneous read.
  This promotes increment 2's deferred peak-hold from a nicety to the core mechanism:
  **an instantaneous sample at 10 Hz misses the peak of a spike that lasted 20 ms**,
  and the plotted amplitude would then depend on sampling phase. An envelope makes
  spike amplitudes exact **at any TX rate**, which decouples the plot's correctness from
  this ADR's rate decision entirely.

**Event markers need nothing new.** `St` transitions carry ignition and apogee at
**sample** accuracy, not TX accuracy, because MET zero is backdated to the accel gate
(`launch::Confirm::launch_ms()`) and `St:2` entry is the confirmed-apogee instant. The
vertical lines on the plot are already available.

Worst case, **with the range assumptions recorded** — the absence of which caused a
107-vs-113-vs-109 disagreement that no one could adjudicate:

| field | worst form | assumption |
|---|---|---|
| existing 12 tags | — | `ALT` <20000 ft, `Max` <200000 ft, `G`/`Pg` <200.0, `T` <100.0 °C, `Batt` <100.00 V, `SEQ`/`MET` 16-bit |
| `Vel` | `Vel:-1999.9` | ±1999.9 ft/s (F15 burnout ≈875 ft/s → 2.3× margin) |
| `Gmx` | `Gmx:199.9` | 0.0–199.9 g |
| `Gmn` | `Gmn:199.9` | 0.0–199.9 g; **worst FORM is the longest, not the value floor** (corrected, Amendment 1) |

**109 B today → 141 B** (corrected from 139, Amendment 1). Buffer sizing superseded by
Amendment 1: **`char msg[256]`**, sized to the largest frame (hard cap 251 =
`RH_RF95_MAX_MESSAGE_LEN`, above which `send()` transmits nothing).

## 5. Why not subcadence

Sending slow-changing tags (`Max`, `Pg`, `T`, `Batt`) on every Nth packet is legal
within v1 — ADR 0001 declares missing tags valid — and would save ~30 B.

**Rejected, because it trades a real property for a marginal one.** The saving is ~13 %
of air time; the cost is that **every consumer must now handle a packet that is missing
fields it saw a moment ago**, and every derived series acquires holes at a cadence
unrelated to anything physical. The sentinel-versus-legal-value class this project keeps
finding (`Max:0` pre-launch, `SEQ→0`, `ALT→0` coalescing) lives exactly in that
territory: **"absent" and "unchanged" become indistinguishable downstream.** BW500
already buys the head-room outright, so the complexity has nothing to buy.

## 6. The ASCII tax, acknowledged

`KEY:VALUE` ASCII is expensive: 139 B carries roughly 15 numbers that would fit in
about 30 bytes packed — **a tax of roughly 4×.** Removing it would raise the ceiling far
past anything bandwidth can offer.

**It is not being removed now, deliberately.** ASCII is why the format is debuggable at
a serial console, greppable in a session log, tolerant of unknown tags, and survivable
across version skew — the properties that have made every prior epic cheap. A binary
format is a **v2 decision** with its own ADR: it breaks every consumer at once, needs a
schema and a code generator, and forfeits the "read the log with your eyes" property
that has repeatedly been how defects here were actually found.

**Recorded as the known future option**: if a rate beyond ~17 pkt/s is ever needed, the
next lever is encoding, not bandwidth — bandwidth is exhausted at BW500.

## 7. Consequences

- **The receiver must be reconfigured identically.** This is a **both-ends constant**
  (`ground/rx/sx127x.py` modem config vs. the sled's RadioHead setup). Its failure mode
  is **silent total link loss** — no error, simply no packets — so it is a coordinated
  cutover and a prime restated-fact hazard. The bandwidth value must have **one
  authority** and be cited, not copied.
- **`waitPacketSent()` must become non-blocking first.** At 58.9 % duty a blocking
  transmit would consume the sample loop it exists to serve. Measured: transmission
  already steals ~33 ms of every 59 ms sample period today.
- **`ground/baseline.py WINDOW = 15` must become time-based before the rate rises.** It
  is a *sample* count calibrated in *seconds*; at 10 Hz the AGL baseline would silently
  lock on 1.5 s of data instead of 15 s. Same class as the 84 ft error `max_is_meaningful`
  exists to prevent.
- **`encode_packet` truncation must be made loud.** Verified today: on overflow it
  returns `out_len − 1`, a valid-looking length, and the fragment is transmitted. Against
  the repo's own decoder, a frame cut at 105 B decodes as a **valid packet with
  `MET:6` where the true value is 65535** — no counter moves. Adding fields without
  fixing this converts a size problem into silent data corruption.
- **`MET` becomes a staircase** at whole-second resolution — 10 packets share a value.
  `received_at` preserves ordering. **Do not change MET's units; that is a `V:2` bump.**

## 8. The gate this decision is blocked on

**Ground RX turn time.** At 10 Hz a packet arrives every **100 ms** into a
**single-packet FIFO** on a **polling** driver with no DIO0 interrupt wired. If the RX
loop's worst-case turn does not clear 100 ms with margin, packets are overwritten in the
FIFO and lost **before any loss statistic can see them** — the loss would be invisible
in exactly the place we would look for it.

The worst case is **not** the poll cadence: `service.py` sleeps 20 ms *only when no
frame is waiting*, so with packets flowing the loop is tight. The worst case is the
**1 Hz turn**, which additionally runs `heartbeat.publish()` and `_view_model()`.

**MEASURED 2026-08-06 — THE GATE PASSES.** Instrumented `service.py` on the real box under
real load, OLED render thread running, heartbeat taking its success path:

| | p50 | p95 | p99 | **max** |
|---|---|---|---|---|
| frame-turns (n=70) | 1.43 | 1.69 | 6.77 | **6.77 ms** |
| heartbeat-turns (n=69) | 20.40 | 20.49 | 24.34 | **24.34 ms** |
| all-turns (n=3518) | 20.15 | 20.28 | 20.42 | **25.65 ms** |

**Worst observed turn 25.65 ms against a 100 ms budget — 26 % of budget, ~3.9x margin.**
Most of that is the *deliberate* 20 ms idle sleep, which does not occur when frames are
queued; actual packet processing is **1.43 ms typical, 6.77 ms worst**.

**Caveat, stated because it bounds the claim:** measured at the sled's current **1 Hz**
arrival rate, not 10 Hz. Per-turn WORK is the relevant quantity and does not scale with
arrival rate, but this is not a 10 Hz load test — the sustained 10 Hz bench remains the
final flight gate regardless of this ADR's status.

**ADR STATUS AND FLIGHT DECISION ARE SEPARATE THINGS.** This ADR being ACCEPTED records
that the design is decided and its gate measured; it does NOT authorise a flight. The
flight is separately gated on the repaired pigtail and the §2 RSSI validation.

**Documented fallback if the turn cannot clear 100 ms: 5 Hz at BW250** — 117.9 ms ToA,
58.9 % duty, a 200 ms RX budget, and **−120 dBm sensitivity, 3 dB better than BW500**.
It yields ~100 points per flight instead of ~200: a materially poorer plot, but the same
plot. The alternative to the fallback is wiring DIO0 for interrupt-driven receive, which
removes the polling constraint entirely and is the better long-term answer.

## 9. Alternatives considered

| Option | Verdict |
|---|---|
| Stay at 1 Hz | Rejected — ~20 points per flight; the plot is the requirement |
| 20 Hz TX | Rejected — 118 % duty even at BW500; above the RF ceiling |
| SF6 | Rejected — implicit header fights variable-length ASCII (§1) |
| Subcadence slow tags | Rejected — "absent" vs "unchanged" ambiguity for ~13 % (§5) |
| Binary v2 encoding | Deferred — real ~4× win, breaks every consumer; own ADR (§6) |
| Ground-derived velocity | Rejected — differentiating 10 Hz `ALT` yields noise (§4) |
| **10 Hz @ SF7/BW500/17 dBm** | **Decided, pending §8** |
| 5 Hz @ SF7/BW250 | Documented fallback if §8 fails |

---

# Amendment 1 — 2026-08-08: 9-DoF fit, the E+F frame split, and the corrected worst case

**Status:** ACCEPTED (decision by Frank, 2026-08-08). Measured numbers marked *pending
bench* are completed at build close-out.

## A1.1 Correction to §4 — worst FORM, not value floor

§4 sized `Gmn`'s worst form as `Gmn:0.0` because the value's floor is 0. For buffer and
ToA sizing the worst form is the **longest** — `Gmn:199.9` (min |g| across a boost window
is large, not small). The base worst case is therefore **141 B, not 139**. ToA at
SF7/BW500 is unchanged (58.94 ms) only because payload symbols come in 5-symbol groups
and the ceiling absorbed the difference — the number was wrong even though the conclusion
survived, which is why it is corrected rather than waved through.

## A1.2 The 9-DoF fit result that forced a decision

Adding six raw channels (gyro xyz, mag xyz) to the flight frame at 10 Hz:

| variant | bytes | duty @10 Hz |
|---|---|---|
| full 9-DoF, 1 decimal | 210 | **84.5 %** |
| full 9-DoF, integer | 198 | **80.7 %** |
| gyro only, integer, no mag | 171 | **70.5 %** |
| \|gyro\| envelope pair (`Wmx`/`Wmn`) | 163 | **67.9 %** |
| \|gyro\| max only (`Wmx`) | 152 | **64.1 %** |

The pre-agreed acceptance line was **65 % duty**, which corresponds to a **155 B** frame —
a **14 B** budget over the 141 B base. **No 3-axis representation of anything fits in
14 B.** This is structural, not marginal: reduced precision recovers 12 of the needed 69
bytes, and even dropping magnetometer entirely at integer precision misses the line.

## A1.3 The decision: E+F — envelope in flight, raw channels on the pad

- **FLIGHT frame (St:1 / St:2, 10 Hz): base + `Wmx`** — **152 B, 64.1 % duty.**
- **PAD frame (St:0, 1 Hz): base + `Gyx Gyy Gyz Mgx Mgy Mgz`** — **210 B, 8.5 % duty.**

Both shapes are v1-legal under ADR 0001's additive/missing-tag tolerance; a pad-shaped
frame arriving mid-transition decodes by the additive rules, not by special-casing.

**Why flight carries a magnitude envelope and not raw channels — the aliasing argument.**
At plausible spin rates (> 5 Hz), 10 Hz samples of instantaneous gyro are spectrally
aliased regardless of encoding; the in-flight raw channels were only ever fusion-reference
input, never spin spectra. `Wmx` is the window **max of |ω| over the ~22 Hz onboard
samples**, so spin *magnitude* survives unaliased at any TX rate — the same trick that
justified `Gmx`/`Gmn` for accel spikes. What is genuinely lost in flight: spin phase and
attitude reference.

**Why the pad frame carries the raw channels — the calibration argument.** Ground-side
fusion (Epic 5) needs stationary bias-reference data more than it needs aliased flight
samples. Raw 9-DoF at 1 Hz on a stationary pad is exactly that record, captured where it
is most useful, at 8.5 % duty.

## A1.4 Frame tables with per-field range assumptions

Existing 12 tags: assumptions as §4. New fields:

| tag | frames | worst form | unit | range assumption |
|---|---|---|---|---|
| `Vel` | both | `Vel:-1999.9` | ft/s | ±1999.9 (F15 burnout ≈ 875 → 2.3× margin) |
| `Gmx` | both | `Gmx:199.9` | g | window max of \|accel\|, 0–199.9 |
| `Gmn` | both | `Gmn:199.9` | g | window min of \|accel\|; longest form governs |
| `Wmx` | flight | `Wmx:2293.8` | dps | window max of \|gyro\|; LSM6DSOX ±2000 dps FS reports to ±2293.8 (int16 × 70 mdps/LSB) |
| `Gyx/Gyy/Gyz` | pad | `-2293.8` | dps | raw gyro, same FS |
| `Mgx/Mgy/Mgz` | pad | `-478.9` | µT | raw mag; LIS3MDL ±4 gauss FS → ±478.9 µT (int16 / 6842 LSB/gauss × 100) |

Tag names are contract-level and were gated on the collision proof
(`docs/newtag-collision-proof.md`) against every special-cased name in the ground
pipeline and ADR 0001 Appendix A's rules (`Roll`/`Spin` stay reserved for fusion
outputs; raw channels must not squat on them).

**Buffer: `char msg[256]`**, sized to the largest frame (210 B pad), under the 251 B
`RH_RF95_MAX_MESSAGE_LEN` cap. Range assumptions live beside the constant in a comment
block so the number cannot drift from its justification.

## A1.5 Binary v2 — deferred again, with the trigger on record

Binary encoding is NOT taken now, for three reasons with evidence attached:

1. **It does not cure the problem that motivates it here.** At 10 Hz TX, in-flight raw
   gyro is aliased whatever the encoding (A1.3); binary would shrink the frame without
   restoring the signal.
2. **It is the largest contract change this system has** — it re-opens framing,
   versioning, absent-vs-zero semantics via presence encoding, the session storage
   format, a dual-format transition window, and full fixture regeneration.
3. **It deserves its own epic, ADR and red team, AFTER the pigtail and the flight.**

**Forcing functions now on record: the ASCII tax (§6), the 9-DoF fit failure (A1.2), and
duty pressure at 10 Hz. When a fourth arrives, that is the trigger** to open the binary
v2 epic — not before.

## A1.6 Both-ends constants and measured numbers — *pending bench*

Completed at build close-out: the sled-side and Pi-side bandwidth constants cited
side-by-side by file:line (§7's silent-total-link-loss hazard), and the measured achieved
sample rate, RX-turn distribution at real 10 Hz arrival (closing §8's 1 Hz-arrival
caveat), skipped-TX count, and battery draw at the new duty — replacing every estimate
above that a bench can measure.
