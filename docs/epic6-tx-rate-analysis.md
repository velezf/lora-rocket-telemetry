# Epic 6 — Maximum TX rate: RF ceiling and ground impact

**Status: ANALYSIS ONLY. Nothing here is implemented.** Phase 1 deliverable.
**Base commit: `5642627`** (branch `feat/epic6-tx-rate`, worktree `/private/tmp/wt-epic6`).
Anything committed only on another branch is invisible to this analysis (parallel-agent rule 8).

**No hardware was touched.** Every number below is either computed here or read out of a file in
this repo; the two things that need the bench are listed in §8 with the exact commands.

## 0. The problem

A 20 s flight at 1 Hz TX yields **20 data points for the entire flight** and **1.6 points across the
1.6 s motor burn** (`firmware/lib/profile/profile.h:22` — `burn_s = 1.6`). The sled already SAMPLES at
a measured 17.00 Hz; the throttle is `TX_MS` in `firmware/src/main.cpp:111`.

| TX rate | points / 20 s flight | points across the 1.6 s burn |
|---|---|---|
| 1 Hz (today) | 20 | 1.6 |
| 2 Hz | 40 | 3.2 |
| 5 Hz | 100 | 8.0 |
| 10 Hz | 200 | 16.0 |
| 20 Hz | 400 | 32.0 |

---

## 1. The radio configuration — READ, not assumed

`firmware/src/main.cpp:79-81` calls `rf95.init()`, `setFrequency(434.0)`, `setTxPower(23, false)`
and **nothing else**. So every modem parameter is the RadioHead default, which
`.pio/libdeps/feather_m0_tx/RadioHead/RH_RF95.cpp:133-134` sets as
`setModemConfig(Bw125Cr45Sf128)` + `setPreambleLength(8)`. That table entry
(`RH_RF95.cpp:24`) writes registers `0x1D=0x72, 0x1E=0x74, 0x26=0x04`, which decode as:

| Parameter | Value | Where it comes from |
|---|---|---|
| Bandwidth | **125 kHz** | `0x1D` bits 7:4 = `0x7` |
| Coding rate | **4/5** | `0x1D` bits 3:1 = `0b001` |
| Header | **explicit** | `0x1D` bit 0 = 0 |
| Spreading factor | **SF7** | `0x1E` bits 7:4 = `7` |
| Payload CRC | **on** | `0x1E` bit 2 = 1 |
| LowDataRateOptimize | **off** | `0x26` bit 3 = 0 |
| Preamble | **8 symbols** | `setPreambleLength(8)` |
| TX power | **23 dBm** (PA_BOOST) | `main.cpp:81` |
| Frequency | **434.0 MHz** | `main.cpp:39` |

The Pi RX mirrors this in `ground/rx/sx127x.py:62-71` (`LoRaConfig` defaults). **Both ends are
independently hard-coded; there is no negotiation.** A change on one end alone is total,
silent link loss — the same failure class ADR 0001 already warns about for CRC.

Two further facts read from RadioHead, both load-bearing below:

- **`rf95.waitPacketSent()` is a hard busy-wait** — `RHGenericDriver.cpp`:
  `while (_mode == RHModeTx) YIELD;`. The Feather's `loop()` cannot sample while it spins.
- **`waitCAD()` returns immediately** — `_cad_timeout` defaults to 0 and `main.cpp` never calls
  `setCADTimeout()`. **There is no listen-before-talk.** Airtime collisions are unmanaged.

---

## 2. Payload size — MEASURED with the real encoder

Measured by compiling `firmware/lib/packet/packet.cpp` on the host and calling `encode_packet`
(the same function the sled runs). RadioHead adds a **4-byte header** (TO/FROM/ID/FLAGS,
`RH_RF95.cpp` `send()`), so PHY payload = app bytes + 4.

| Frame | app bytes | PHY bytes |
|---|---|---|
| Real pad frame (`SEQ:193 St:0 ALT:-83ft Max:0ft …`) | **84** | 88 |
| ADR 0001 golden vector / typical in-flight frame | **88** | 92 |
| Realistic in-flight worst (SEQ 65535, ALT −12345, ADXL clip `G:346.4`) | **102** | 106 |
| **Absolute worst, every field saturated — CURRENT field set** | **113** | 117 |
| Absolute worst **+ `Ax`/`Ay`/`Az`** (increment 2) | **143** | 147 |

**Correction to `docs/RESUME.md:63`: the current worst case is 113 bytes, not 107.**
I could not reproduce 107 from the encoder under any saturation assumption. 113 is the value that
falls out of `worst_case_input()` in increment 2's `firmware/test/test_packet/test_packet.cpp:131`
with the three axis tags removed, and it reconciles exactly with the documented with-accel figure:
**113 + 30 (` Ax:-200.0 Ay:-200.0 Az:-200.0`) = 143**, matching `docs/increment2-adxl-notes.md`.
107 appears to be a transcription slip. Nothing depends on it — `PACKET_BUF_LEN = 160` is still
correct with 17 bytes of headroom — but the number should be fixed where it is stated.

---

## 3. The RF ceiling — Semtech LoRa time-on-air

Standard SX1276 formulation:

```
Ts       = 2^SF / BW                                        (symbol time)
Tpre     = (n_preamble + 4.25) * Ts
nsym     = 8 + max( ceil( (8*PL - 4*SF + 28 + 16*CRC - 20*IH) / (4*(SF - 2*DE)) ) * (CR+4), 0 )
ToA      = Tpre + nsym * Ts
```
with `PL` = PHY payload bytes, `CRC=1`, `IH=0` (explicit header), `CR=1` (4/5),
`DE=1` iff `Ts > 16 ms` (never, at SF7/BW125).

**Worked, at the current config (SF7/BW125, PL = 92 for a typical 88-byte frame):**

- `Ts = 128 / 125000 = 1.024 ms`
- `Tpre = 12.25 x 1.024 = 12.544 ms`
- numerator `= 8(92) - 4(7) + 28 + 16 - 0 = 736 - 28 + 44 = 752`; denominator `= 4(7) = 28`
- `ceil(752/28) = ceil(26.857) = 27`; `nsym = 8 + 27 x 5 = 143`
- `Tpayload = 143 x 1.024 = 146.432 ms`
- **`ToA = 12.544 + 146.432 = 158.976 ms`**

| Frame | ToA @ SF7/BW125 | 100 %-duty ceiling |
|---|---|---|
| 84 B pad frame | 153.86 ms | 6.50 pkt/s |
| **88 B typical** | **158.98 ms** | **6.29 pkt/s** |
| 102 B realistic worst | 179.46 ms | 5.57 pkt/s |
| **113 B saturated worst** | **194.82 ms** | **5.13 pkt/s** |
| 143 B with-accel worst | 240.90 ms | 4.15 pkt/s |

**The hard ceiling at today's radio settings is ~5.1 pkt/s** (sized on the worst case, not the
typical one — a rate you cannot sustain on your worst frame is not a rate).

### What actually limits it — and it is NOT the regulation

This is amateur service under **Part 97** (KC3ZTQ). **There is no regulatory duty-cycle limit**
and no 400 ms dwell rule; the ISM/LBT arithmetic that constrains a commercial 868/915 MHz node
does not apply. The real limits, in the order they bite:

1. **SLED CPU — this is the binding constraint, and it is not obvious.** See §4. Sampling
   degrades from the first step up (17 → 13.6 Hz at 2 Hz TX) and crosses **below the 8 Hz abort
   floor at ~3.8 Hz TX** — before the 5.1 pkt/s RF ceiling is ever reached. Fixable
   (§9.1a), which is why it is first: unfixed, it is the ceiling.
2. **Airtime collision.** At 5 Hz / 79.5 % duty the channel is almost fully occupied by one sled,
   with `waitCAD` disabled. The Epic 7 lander (`SRC:2`) sharing 434.0 MHz would collide
   constantly. The Epic 6 rider "±10 % TX-interval jitter" (`docs/RESUME.md:552`) is anti-lockstep
   for *simultaneous* birds; it does not create airtime that isn't there.
3. **Sled battery.** RFM95 at +23 dBm PA_BOOST is roughly 120 mA. At 40 % duty that is ~48 mA
   of continuous average draw added to the sled — irrelevant for 20 s of flight, and a real
   problem if the rate never drops back (§5).
4. **Thermal.** Not a factor for a 20 s burst at these powers.

**Not one of these is law.** The ADR 0001 "negligible at 1 Hz" note (`docs/adr/0001-packet-format-v1.md:107`)
is the assumption this work retires.

---

## 4. THE HEADLINE FINDING: TX blocks sampling, so raising the rate destroys detection

`firmware/src/main.cpp:176-177` does `rf95.send(...)` then `rf95.waitPacketSent()`, which busy-waits
for the **entire** time-on-air. During that window `loop()` never reaches the SAMPLE branch. So:

```
achieved sample Hz  =  20 Hz  x  (1 - tx_hz x ToA)          [while the sensor tick fits in SAMPLE_MS]
```

**This model reproduces the flown measurement.** At the flown config (TX 1 Hz, 84–88 B frames):
`20 x (1 - 0.15898) = 16.82 Hz`, and `20 x (1 - 0.15386) = 16.92 Hz` for the 84 B pad frame.
**Measured: 17.00 Hz** (`docs/RESUME.md:27`). Agreement within ~0.5 %.

**This contradicts the explanation currently in RESUME.** `docs/RESUME.md:29-30` and the backlog
item at `docs/RESUME.md:76-78` attribute the 20 → 17 Hz shortfall to BMP390 conversion time
(~59 ms per sample, of which 16.3 ms is 8x temperature oversampling). But 59 ms/sample *combined
with* the 159 ms/s of blocking TX predicts `(1000 − 159) / 59 = 14.25 Hz`, which is 16 % below the
measured 17.00. **The sensor tick must actually be fitting inside the 50 ms budget**, and the
entire shortfall is the blocking transmit.

Consequence: **"drop the BMP390 temperature oversampling from 8x" buys back nothing.** It is not a
harmful change, but it is not the sample-rate lever it is recorded as being. This is a hypothesis
with a one-line falsification test — see §8, M1. **It should be settled before that backlog item
is worked**, and it should be settled before any TX-rate change, because it determines whether
non-blocking TX is sufficient on its own.

### 4.1 The coupling, tabulated — under BOTH sample-cost models

Two models are in play and they disagree, so both are carried rather than one being picked:

- **MODEL A (tick-limited)** — the sensor tick fits inside `SAMPLE_MS = 50 ms`, so the loop
  free-runs at **20.00 Hz** and the *only* thing stealing ticks is the blocking transmit.
  `achieved = 20 x (1 - tx_hz x ToA)`.
- **MODEL B (sensor-limited)** — the BMP390 + ADXL tick really costs **59 ms**
  (`docs/RESUME.md:29-30`), so the loop free-runs at 16.95 Hz *and* loses ticks to TX.
  `achieved = (1 - tx_hz x ToA) / 0.059`.

**Typical 88-byte frame — ToA = 158.98 ms**

| TX Hz | blocking ms/s | duty | ticks lost/s (A, 50 ms) | **A: achieved** | samples lost/s (B, 59 ms) | **B: achieved** |
|---|---|---|---|---|---|---|
| 1 | 159 | 15.9 % | 3.2 | **16.82 Hz** | 2.7 | 14.25 Hz |
| 2 | 318 | 31.8 % | 6.4 | **13.64 Hz** | 5.4 | 11.56 Hz |
| 3 | 477 | 47.7 % | 9.5 | **10.46 Hz** | 8.1 | 8.87 Hz |
| 4 | 636 | 63.6 % | 12.7 | **7.28 Hz** | 10.8 | 6.17 Hz |
| 5 | 795 | 79.5 % | 15.9 | **4.10 Hz** | 13.5 | 3.48 Hz |
| 6 | 954 | 95.4 % | 19.1 | **0.92 Hz** | 16.2 | 0.78 Hz |

**Saturated worst 113-byte frame — ToA = 194.82 ms**

| TX Hz | blocking ms/s | duty | ticks lost/s (A) | **A: achieved** | samples lost/s (B) | **B: achieved** |
|---|---|---|---|---|---|---|
| 1 | 195 | 19.5 % | 3.9 | **16.10 Hz** | 3.3 | 13.65 Hz |
| 2 | 390 | 39.0 % | 7.8 | **12.21 Hz** | 6.6 | 10.35 Hz |
| 3 | 584 | 58.4 % | 11.7 | **8.31 Hz** | 9.9 | 7.04 Hz |
| 4 | 779 | 77.9 % | 15.6 | **4.41 Hz** | 13.2 | 3.74 Hz |
| 5 | **974** | **97.4 %** | 19.5 | **0.52 Hz** | 16.5 | 0.44 Hz |
| 6 | 1169 | 116.9 % | — | **SAMPLING STOPS** | — | **SAMPLING STOPS** |

**Frank's arithmetic is confirmed exactly.** "~200 ms ToA, ~1000 ms of blocking per second at
5 Hz, leaving no loop time to sample" = the 113 B row: **194.82 ms x 5 = 974 ms/s, 97.4 % duty,
0.52 Hz sampling.** On the typical 88 B frame it is 795 ms/s and 4.10 Hz. **Both are catastrophic**
and the conclusion does not depend on which frame size or which sample model you use.

**Where it collapses:** sampling crosses **below the 8 Hz abort floor** (`docs/RESUME.md:31`)
between **2 and 3 Hz** on the worst-case frame, and between **3 and 4 Hz** on the typical one.
**That is the real ceiling today — roughly 3 Hz, not the 5.13 pkt/s airtime ceiling of §3.**

At 5 Hz blocking, `apogee::Confirm`'s 300 ms dwell (`firmware/src/main.cpp:57`) is **one sample**
and `launch::Confirm`'s 100 ms dwell (`main.cpp:54`) is **zero samples** — silently degrading it
back to the single-sample latch it was written to remove. Both are documented as *"constants are
in TIME, not sample counts"* so they lose resolution rather than break outright, but a dwell
resolved by one sample is not a dwell. **More packets carrying worse flight-state is a net loss.**

### 4.2 Which model is right — the measurement discriminates, but confirm it

| | prediction at TX 1 Hz, 84 B pad frame | prediction, 88 B | **measured** |
|---|---|---|---|
| MODEL A | **16.92 Hz** | 16.82 Hz | **17.00 Hz** |
| MODEL B | 14.34 Hz | 14.25 Hz | **17.00 Hz** |

The bench run was entirely `St:0` pad frames (`docs/RESUME.md:36-37` — `St` was `[0]` only across
all 115 packets), i.e. the 84 B frame. **Model A predicts it to within 0.5 %; Model B is 16 % low.**
The achieved-rate reporter is unbiased for this purpose: `sampleWindowStart` and `now` are both
captured at the top of `loop()` before the transmit (`main.cpp:124,182-186`), so a 5 s window
contains exactly 5 transmits, and `sampleCount` counts loop ticks whenever `baroFailures` is 0.

**So the 59 ms/sample figure and the 17.00 Hz figure cannot both be true**, and the difference
matters for what the fix buys: under A, non-blocking TX restores ~20 Hz; under B it restores only
~17 Hz and the sensor becomes the floor. **The fix is required either way** — only its payoff
changes. §8 M1 settles it with one line of firmware and one serial line of output.

### 4.3 The ceiling BOTH ways — this is the value of the architecture change

Ceiling defined as the highest TX rate that keeps sampling at or above the **8 Hz abort floor**,
sized on the saturated-worst frame and the pessimistic sample model (Model B):

| Radio config | **BLOCKING send (today)** | **NON-BLOCKING send** | gain | sampling at the ceiling |
|---|---|---|---|---|
| **SF7/BW125 (today)** | **2.7 Hz** | **5.13 Hz** (airtime-bound) | **x1.89** | 8 Hz → **~17–20 Hz** |
| SF7/BW250 | 5.4 Hz | 10.27 Hz | x1.89 | 8 Hz → ~17–20 Hz |
| SF7/BW500 | 10.8 Hz | 20.53 Hz | x1.89 | 8 Hz → ~17–20 Hz |

**Two separate wins, and the second is bigger than the first.**
1. **TX rate: x1.89 at every bandwidth** — the ratio is constant because both ceilings are `1/ToA`
   scaled by a different constant, so this is a property of the architecture, not of the radio.
2. **Sample rate stops being collateral damage.** At the blocking ceiling the sled is sampling at
   exactly the abort floor. Non-blocking, it samples at its free-running rate *at any TX rate below
   the airtime ceiling* — **5x better sampling at 5 Hz TX (4.10 → ~20 Hz)**. Since apogee latency
   is the thing Epic 6 Phase 0 exists to reduce (33.8 ft at 20 Hz vs 77.9 ft at 1 Hz,
   `firmware/src/main.cpp:107-108`), **this is the change that actually protects the epic's premise.**

**So the change is not "edit `TX_MS`". The change is "stop blocking on TX, then edit `TX_MS`."**
Costed in §9.1a.

---

## 5. State-dependent rate

ADR 0001 defines exactly three `St` codes: **0 pad / 1 ascent / 2 descent**
(`docs/adr/0001-packet-format-v1.md:47`). **There is no landed code.** `St:3 = landed` is Epic 6
firmware rider #1 (`docs/RESUME.md:548`) and does not exist.

`firmware/src/main.cpp:163` computes `St` from two detectors that **both latch permanently**:
`launch::Confirm::in_flight_` and `apogee::Confirm::descending_` are never cleared
(`firmware/lib/launch/launch_confirm.h:57,61`, `firmware/lib/apogee/apogee_confirm.h:62`).

**Therefore a naive "fast while `St != 0`" rule NEVER TURNS OFF.** After landing the sled keeps
`St:2` until it is power-cycled, so it would sit on the pad, in the car, and on the bench
transmitting at 10 Hz / 40 % duty — draining the sled battery, occupying the channel, and
inflating the session log — with no signal that anything is wrong. **This is the single thing
most likely to be missed when implementing this.**

### Recommended switching logic

```
TX period = TX_PAD_MS (1000)         while !inFlight                       [St:0]
          = TX_FLIGHT_MS             while inFlight && MET < FAST_WINDOW_S  [St:1 / St:2]
          = TX_PAD_MS (1000)         thereafter                            [still St:2]
```

`FAST_WINDOW_S` is a **pure timer bounded off the confirmed-launch instant** — no new wire tag,
no ADR change, no landed detector. 60 s is 3x the expected flight and safely covers a chute
descent. When `St:3` lands (rider #1) the cap becomes a backstop rather than the primary rule.

Transitions are clean in both directions: the TX gate is
`if (now - lastTxMs >= TX_MS)` (`main.cpp:154`), so shrinking the period mid-interval fires the
next packet as soon as the *new* period has elapsed, and growing it simply stretches the next gap.
No glitch, no double-send, no SEQ discontinuity.

**Why this is safe for every ground consumer: `SEQ` counts TRANSMISSIONS, not seconds.**
`main.cpp:179` increments it once per TX regardless of period. So loss accounting is
rate-agnostic *by construction* across a rate change — see §6.1.

### Side benefit

At 1 Hz the first in-flight packet can be up to 1 s late; at 10 Hz it is ≤100 ms. `MET`'s
zero point and the `flight_open` event both sharpen accordingly.

---

## 6. GROUND IMPACT

Ground CPU is **not** a constraint anywhere. Measured on this Mac: the full
decode → record → LinkStats → dispatch(LiveState + LiveFlights) path costs
**9.4 µs/packet (~106,000 packets/s)**; `derive_flights` over 20,000 packet records takes
**0.04 s**. Even a 10x slower Pi has four orders of magnitude of headroom. Everything below is
about *semantics* and *I/O scheduling*, not throughput.

### 6.1 SEQ loss statistics — **SURVIVES** (and this is the load-bearing property)

`ground/linkstats/linkstats.py:91` — `missed = (seq - last_seq - 1) % 65536`.
Same rule in `ground/flights/segmenter.py:184`. Loss percentage is assembled at
`ground/dashboard/model.py:140` (`gaps / (rx + gaps)`) and `ground/publish/data.py:43`.

**Nothing in the loss path reads a clock or assumes a packet interval.** SEQ counts transmissions,
so at any rate — and *across* a state-dependent rate change — a gap of N means N transmissions
missed. Percentages stay comparable across flights at different rates. Nothing to change.

**One semantic change to record, though, and it is not in the code:**

> At 1 Hz, "loss" means RF loss. At 5–10 Hz it also means **ground receiver scheduling latency**,
> and the two are indistinguishable.

`ground/ingest/service.py:218-222` polls `rx.receive()` and `time.sleep(0.02)` when idle. In
RXCONTINUOUS the SX127x writes each new packet over the FIFO region and `RegFifoRxCurrentAddr`
tracks the newest, so a packet that arrives before the previous is read out is **silently
overwritten** — surfacing as a SEQ gap, i.e. as RF loss. At 1 Hz the inter-packet gap is 841 ms
and the 20 ms sleep is irrelevant. At 5 Hz it is **41 ms**, and a 20 ms sleep plus the
`_view_model()` rebuild the loop performs once a second consumes a real fraction of it.

**Recommended, and cheap:** drop the idle sleep to ~2 ms, and count overruns distinctly (a
`RegIrqFlags` RXDONE seen with an unread previous frame). Without a distinct counter, a published
loss percentage silently conflates "the radio link" with "the Python loop was busy" — which is
exactly the class of hidden-provenance defect this project keeps removing.

**SEQ wrap:** at 10 Hz the uint16 wraps every 6,554 s (1.8 h) instead of 18.2 h. The modulo
arithmetic handles it; only a *contiguous outage* longer than the wrap would alias, which a 20 s
flight cannot produce. **Survives.**

### 6.2 The 3 s staleness threshold — **DEGRADES** (loses sensitivity, stays correct)

Two independent copies, both `3.0`:
- `ground/panel/supervisor.py:24-25` — `STALE_S` (ingest heartbeat) and `RX_STALE_S` (link activity)
- `ground/oled/spec.py:37` — `STALE_S`, explicitly *"Matches the RX LED's staleness window so the
  two surfaces agree about what 'quiet' means"*

**`STALE_S` (heartbeat) is unaffected** — the heartbeat is published on its own 1 Hz monotonic gate
inside the RX loop (`ground/ingest/service.py:227`), independent of packet rate. Leave it at 3.0.

**`RX_STALE_S` degrades.** It is 3 missed packets at 1 Hz and 30 at 10 Hz. It stays *correct* —
3 s of silence is still 3 s of silence, and that is the right operator semantic at the pad (the
question `G_RX` answers is "is the sled talking to me", not "what is the loss rate"). But as an
early warning during a 20 s flight, 3 s is now **15 % of the whole flight**.

**Recommendation: split the constant rather than scale it.** `RX_STALE_S` should stay 3.0 as a
*link-alive* signal, because it is read by a human standing at the box before launch and a
faster-blinking `G_RX` is not more informative. If a tighter in-flight signal is wanted it should
be a *new* derived signal (e.g. "received < 50 % of expected in the last second"), not a smaller
timeout — a 0.3 s timeout would make `G_RX` flicker on ordinary single-packet loss and train the
operator to ignore it. **Do not scale this constant with the rate.**

### 6.3 The 90 s silence close — **SURVIVES unchanged**

`ground/flights/segmenter.py:107` (default), `ground/ingest/service.py:55` (field config
`silence_timeout_s`), `ground/flights/cli.py:96` (`--silence` default), `ground/flights/derive.py:32`.
The comparison is `t - fl["t_end"] > self.silence_timeout_s` on a **monotonic clock**
(`segmenter.py:197`) — pure wall-time, no packet-count assumption.

At 1 Hz, 90 s is 90 consecutive missed packets; at 10 Hz it is 900. Both mean the same thing: *the
vehicle stopped sending telemetry* — which `segmenter.py:89-93` states is precisely the intent.
**Nothing to change.** It is *already* a generous margin at 1 Hz; a faster rate only makes it more
generous, and the flight is closed manually or on landing anyway.

**One interaction to be aware of:** with the §5 MET cap, the sled drops back to 1 Hz after landing
and keeps transmitting `St:2`, so the flight stays open until power-off + 90 s, exactly as today.
Unchanged behaviour, but worth naming because a reader may expect the rate drop to close the flight.

### 6.4 OLED trend window — **SURVIVES, and is currently INERT**

`ground/oled/spec.py:42` — `TREND_WINDOW_S = 120.0`, with a comment stating the design choice
explicitly: *"TIME-based, not sample-based: a sample count silently stretches under packet loss."*
`ground/oled/spec.py:118` `trend_window()` filters on `now_s - t <= window_s`. **This is the one
window in the codebase that was built rate-agnostic on purpose, and it holds.** At 10 Hz the strip
covers the same 120 s with 1,200 candidate samples instead of 120; the drawing layer
(`ground/oled/draw.py:122-131`) plots one column per sample into a ~120 px strip, so it would need a
decimation step — a cosmetic fix, not a semantic one.

**However — the trend strip is not wired up at all today.** `ground/ingest/service.py:190` calls
`frame_spec(latest.view, clock=..., tick=tick)` and passes **neither `rx_age_s` nor `last_flight`**,
and `frame_spec` (`ground/oled/spec.py:190-196`) never populates `trend`. So in the running
service: `trend` is always empty, `stale` is always `False`, and `PAGE_SUMMARY` is unreachable.
**Pre-existing and rate-independent** — flagged because "the trend window degrades at N Hz" would
otherwise read as a live risk when the feature is inert.

### 6.5 Pad/AGL baseline — **BREAKS. This is the real ground-side defect.**

`ground/flights/baseline.py:16-17`:
```
WINDOW = 15        # trailing samples (~15 s at the ~1 Hz ground packet rate)
EXCLUDE_TAIL = 2   # drop the final ~2 s pre-boost (handling / boost onset)
```

**These are SAMPLE counts whose calibration is stated in SECONDS, and the conversion is the
packet rate.** The comment says so in as many words. Consumers: `ground/flights/segmenter.py:32`
and `ground/dashboard/model.py:29` (`_HIST_LEN = WINDOW + EXCLUDE_TAIL`), and the lock at
`segmenter.py:131` / `model.py:78`.

At 10 Hz:
- the baseline window becomes **1.5 s**, not 15 s;
- `EXCLUDE_TAIL` drops the last **0.2 s** of pre-boost, not 2 s — so the boost-onset samples it
  exists to exclude land **inside** the averaging window;
- `MAX_STDEV = 2.0 ft` (`baseline.py:18`) is a stability gate calibrated on **F1's real pad noise
  over a 15 s span**. Over 1.5 s the barometer's slow drift is invisible, so the gate passes
  window that would have failed — it gets *easier* to lock a baseline, on *less* evidence.

The published `peak_agl_ft` is `peak_alt_ft - baseline_ft` (`ground/publish/data.py:28,36`), and F1's
own record shows why this matters: a wrong baseline moved the published peak by 84 ft on a 10 ft
flight (`ground/flights/segmenter.py` `max_is_meaningful` docstring). **A silently 10x-shortened
baseline window is exactly the class of defect that produces a plausible wrong number.**

**Fix (must land with, or before, the rate change):** re-express the window in **seconds** and
derive the sample count from the observed inter-packet interval — or, simpler and with no new
inference, keep sample counts but make them a function of a declared `packet_hz`. Either way, both
call sites and the derive path must use the same value so live and rebuild cannot disagree (the
property `derive.py` and `live.py` are built to preserve). **This is TDD-able entirely on the host
with no hardware:** the F1 golden fixture (`ground/flights/tests/fixtures/f1_session.jsonl`) is the
regression guard, and its result must stay byte-identical.

### 6.6 Dashboard live trace — **DEGRADES badly**

`ground/dashboard/model.py:52` — `def __init__(self, trace_len: int = 300):   # ~5 min trace at 1 Hz`.
Applied at `model.py:71`, serialized wholesale at `model.py:158`.

**A SAMPLE count documented in minutes.** At 10 Hz the live chart shows **30 seconds** of history
instead of 5 minutes — and it does so without saying so, which is the same "quiet lie about how much
history you are looking at" the OLED trend comment (`ground/oled/spec.py:40-41`) was written to
avoid. **The two surfaces disagree on this design principle today, and the rate change is what
makes it visible.**

Cost of just enlarging it: the trace is rebuilt by tuple concatenation + slice on **every packet**
(`model.py:71`), i.e. O(trace_len) per packet, and the whole trace is materialised into dicts and
JSON on every `/api/state` poll (`model.py:158`), which the page hits every 1500 ms
(`ground/dashboard/templates/index.html:111`). At 10 Hz with `trace_len = 3000`: 30,000 tuple
element copies/s on the RX thread, and a ~3,000-point JSON payload every 1.5 s. Both are still
cheap in absolute terms (see the 9.4 µs/packet measurement), but the O(n) per-packet rebuild
should become a `collections.deque(maxlen=...)` if the length grows 10x.

**Recommendation:** make it a **time** window (matching the OLED's choice), and decimate for
transport — the chart cannot render 3,000 points meaningfully on a phone anyway.

Also on the dashboard: `ageClass()` at `index.html:44` warns at >5 s and flags stale at >15 s.
Wall-clock, so it **survives**, with the same loss-of-sensitivity note as §6.2.

### 6.7 `MET` resolution — **BECOMES THE LIMITING TIME BASE**

`docs/adr/0001-packet-format-v1.md:54`: `MET` is **int seconds**. `firmware/src/main.cpp:170`
computes `(now - launchTime) / 1000UL`.

At 10 Hz, **ten consecutive packets carry the same `MET`**. `MET` is exported as a column
(`ground/flights/export.py:13`) and shown on the dashboard (`ground/dashboard/model.py:156`). As a
plot axis it becomes a staircase.

The usable time axis is `received_at` (ISO with **milliseconds**, `ground/ingest/service.py:44`),
which the dashboard already uses (`index.html:99`) and which the CSV export carries. **So nothing
breaks** — but anyone plotting against `MET` gets 1 s bins.

**Do NOT "fix" this by changing `MET`'s units.** ADR 0001's versioning rule
(`docs/adr/0001-packet-format-v1.md:91-95`) is explicit that changing an existing tag's units
**bumps `V` to 2**. If sub-second onboard time is wanted it must be a **new additive tag**
(a no-bump change), and it should be justified on its own merits — `received_at` already answers
the question at ms resolution.

### 6.8 Session file growth — **SURVIVES with enormous margin**

Measured: **312.4 bytes/record** mean over the 94 packet records in
`ground/flights/tests/fixtures/f1_session.jsonl`; **320.3 bytes/record** for a synthetic 88 B frame.
Using 320 B:

| rate | B/s | 20 s flight | 2 h pad session | 8 h day | days to fill the 32 GB SD |
|---|---|---|---|---|---|
| 1 Hz | 320 | 6.3 kB | 2.3 MB | 9.2 MB | 1,156 |
| 5 Hz | 1,602 | 31 kB | 11.5 MB | 46 MB | 231 |
| 10 Hz | 3,203 | 63 kB | 23 MB | 92 MB | 116 |
| 20 Hz | 6,406 | 125 kB | 46 MB | 185 MB | 58 |

(Pi 5 8 GB RAM + SanDisk Ultra 32 GB microSD, `docs/PROJECT_PLAN.md:33,41`. Free space on the
actual card is unverified — see §8, M2.) **Storage is a non-issue.** Note the ~3.6x expansion from
88 wire bytes to 320 log bytes: the record carries both the typed `fields` dict and the verbatim
`raw` string by design (`ground/sessionlog/records.py:8-9`), which is worth keeping.

**Whole-file readers — the one thing worth watching:**
`ground/flights/cli.py:23` `_read_jsonl` does `p.read_text().splitlines()` and builds a list of
parsed dicts. It is used by `rebuild` (`cli.py:41`) and `export`, and `ground/flights/derive.py:51`
holds a second list of `(t, order, kind, record)` tuples over the same objects.
Measured: **2,097 bytes per parsed record** — a 6.5x expansion over the JSONL.

| session | records | file | RSS if fully parsed |
|---|---|---|---|
| 1 Hz, 2 h | 7,200 | 2.3 MB | 15 MB |
| 10 Hz, 2 h | 72,000 | 23 MB | **151 MB** |
| 20 Hz, 8 h | 576,000 | 185 MB | **1.21 GB** |

On an 8 GB Pi even the pathological row survives, and `derive_flights` at 20,000 records took
0.04 s. **Survives** — but the pathological row is a real number, and `flights rebuild` is run
on the box. If sessions ever get long at 20 Hz, `_read_jsonl` should become a generator; today it
does not need to.

### 6.9 Anything else that assumes 1 Hz — swept

| Site | Assumption | Verdict |
|---|---|---|
| `ground/ingest/service.py:227` | heartbeat publish gated at 1 Hz monotonic | **survives** — decoupled from packet rate by design |
| `ground/ingest/service.py:144` | `OLED_REDRAW_S = 1.0` render cadence | **survives** — traffic-independent by design |
| `ground/oled/draw.py:37` | `_SHIFT_PERIOD_TICKS = 45` burn-in shift | **survives** — counts render ticks, not packets |
| `ground/panel/supervisor.py:23` | `TICKS_PER_SEC = 8` blink waveform | **survives** — generated, not sampled; unrelated to packets |
| `ground/dashboard/model.py:36` | `EventsRing(maxlen=8)` | **survives** — events are not per-packet |
| `ground/ingest/service.py:131` | `packets_per_min` health figure | **survives** — a rate; the number just gets bigger |
| `ground/decode/v1.py` | pure, stateless | **survives** |
| `handheld/` | no rate-coupled constants found | **survives** |

---

## 7. The link-budget question

**SF is NOT the limiting factor, and it cannot be traded away — the sled is already at SF7, the
fastest spreading factor available in explicit-header mode.** There is nowhere to go down.
SF6 exists but requires implicit-header mode (fixed payload length, no CRC-in-header), which the
ADR 0001 variable-length ASCII format cannot use, and RadioHead does not expose it. **The lever is
BANDWIDTH, not SF.**

Sensitivity derived from first principles (so the working is visible rather than recalled):

```
S = -174 dBm/Hz + 10*log10(BW_Hz) + NF + SNR_min(SF)
```
with `NF = 6 dB` (SX127x typical — **an assumption**) and `SNR_min` = −7.5 dB at SF7, stepping
−2.5 dB per SF. This yields **−124.5 dBm at SF7/BW125**, about 1.5 dB optimistic against the
commonly quoted datasheet figure of −123 dBm; treat every absolute number below as ±2 dB.

Free-space path loss at 434 MHz: `FSPL(dB) = 20*log10(d_m) + 25.200`.

| Config | sensitivity | ToA 88 B | ToA 113 B | 100 %-duty ceiling | range vs today (n=2) | range vs today (n=3) | margin @ 140 m |
|---|---|---|---|---|---|---|---|
| **SF7/BW125 (today)** | −124.5 dBm | 158.98 ms | 194.82 ms | 5.13 /s | ×1.00 | ×1.00 | **79.4 dB** |
| SF8/BW125 | −127.0 | 287.23 | 348.67 | 2.87 /s | ×1.33 | ×1.21 | 81.9 dB |
| SF7/BW250 | −121.5 | 79.49 | 97.41 | 10.27 /s | ×0.71 | ×0.79 | 76.4 dB |
| SF8/BW250 | −124.0 | 143.62 | 174.34 | 5.74 /s | ×0.94 | ×0.96 | 78.9 dB |
| **SF7/BW500** | **−118.5** | **39.74** | **48.70** | **20.53 /s** | **×0.50** | **×0.63** | **73.4 dB** |
| SF9/BW500 | −123.5 | 128.26 | 158.98 | 6.29 /s | ×0.89 | ×0.92 | 78.4 dB |

(Ceilings sized on the 113 B saturated worst case. `n` is the path-loss exponent: n=2 is free space,
n=3 is a common near-ground/foliage approximation. The *ratios* are far more trustworthy than any
absolute range, since they depend only on `n`.)

**The absolute range numbers are not worth quoting and I will not dress them up.** Free space with
0 dBi antennas and zero fade margin puts SF7/BW125 at 1,308 km, which is nonsense; the same budget
at n=3 gives 12 km, which is merely optimistic. **What is trustworthy is the margin at the range
that matters.** A 460 ft apogee is ~140 m slant range. Free-space received power at 140 m is
**−45.1 dBm**, leaving **79.4 dB of margin** over today's sensitivity.

**The user's framing is correct and the arithmetic supports it.** Moving to BW 500 kHz costs
**6 dB out of ~73–79 dB of margin** and buys **4x the airtime** (ToA 158.98 → 39.74 ms). For
calibration: F1's measured RSSI was −38 to −14 dBm (`docs/RESUME.md:603`) — that is 80–104 dB above
the SF7/BW500 sensitivity floor, on the bench. **Link budget is not the constraint at this scale;
it is not close.**

**Caveat that is not a formality:** doubling bandwidth also doubles the frequency-error tolerance
required, and 434 MHz crystal offset between two boards is a real effect. BW500 is *more* tolerant
of offset than BW125, so this cuts the safe way — but it has never been measured on these two
radios, and the failure mode is silent (§8, M3).

---

## 8. What needs a bench, and the exact command

**Nothing in §§1–7 required hardware. These do.** For each: the command, and what each outcome means.

### M1 — Is the 17.00 Hz shortfall blocking TX, or the BMP390? (§4)

Settles a contradiction between this analysis and `docs/RESUME.md:29-30`, and decides whether
non-blocking TX alone is enough. **Requires a one-line `main.cpp` change, which I must not make** —
proposed as a patch in §9.

```
# temporarily set TX_MS to 10000 in firmware/src/main.cpp, then:
~/.platformio/penv/bin/pio run -e feather_m0_tx -t upload
~/.platformio/penv/bin/pio device monitor -b 115200 | grep RATE
```

- **`RATE: ~20 Hz`** → this analysis is right; TX blocking is the entire shortfall; the BMP390
  oversampling backlog item buys nothing and should be re-scoped; non-blocking TX is sufficient.
- **`RATE: ~17 Hz`** → the sensor tick really is ~59 ms and my model is wrong; the sample budget
  is sensor-bound, and both the oversampling change *and* non-blocking TX are needed.
- **anything else** → neither model holds; do not proceed on either.

### M2 — Free space on the Pi's SD card (§6.8)

```
ssh rocketman@apogee-gs.local 'df -h / && du -sh ~/apogee-data'
```
Sizing above assumes a 32 GB card. Anything above ~2 GB free makes storage a non-issue at any
rate considered here.

### M3 — The bandwidth cutover, if it is taken (§7)

**Both ends must change in one step; a mismatch is total link loss with no error** — the exact
failure ADR 0001's bring-up check warns about (`docs/adr/0001-packet-format-v1.md:74-78`).
Sled: `RegModemConfig1` becomes `0x92` for BW500 (`0x82` for BW250). Pi:
`LoRaConfig(bandwidth_khz=500)` in `ground/ingest/service.py:118` — `_BW_CODES`
(`ground/rx/sx127x.py:56`) already supports both, so the Pi side is a one-word change.

```
# after flashing the sled AND deploying the Pi change (sanctioned deploy path, RESUME):
ssh rocketman@apogee-gs.local 'journalctl -u apogee-ingest -f' | grep -c 'ADR'
```
Re-run the Epic 3 e2e gate (22/22 ADR-OK, 0 CRC errors) before trusting any flight.
**Recommended: bench this with the sled a few metres away first, then at ~100 m before flying it.**

### M4 — RX-loop overrun at the chosen rate (§6.1)

At the target rate, on the bench, compare the sled's serial `TX:` SEQ stream against the Pi's
`packets_rx`/`packets_lost`. Any loss at <5 m range is **not** RF loss — it is the RX loop dropping
frames, and it must be fixed (shorter idle sleep) before the rate is trusted, because it would
otherwise be published as link loss.

---

## 9. What would have to change

### 9.1 `firmware/src/main.cpp` — PROPOSED DIFF, NOT APPLIED

**I did not edit this file** (single-owner rule). Two independent changes; **the first is required
before the second is safe.**

**(a) Non-blocking TX — required (§4).**

```diff
@@ firmware/src/main.cpp  (TRANSMIT branch, ~line 154)
-  if (now - lastTxMs >= TX_MS) {
+  // Do not start a transmit while one is still in the air: RH_RF95::send() opens with its
+  // own waitPacketSent(), so without this guard the block simply moves here and loop()
+  // still cannot sample. With it, sampling continues THROUGH the transmit.
+  if (now - lastTxMs >= TX_MS && rf95.mode() != RHGenericDriver::RHModeTx) {
     lastTxMs = now;
@@  (end of the TRANSMIT branch, ~line 177)
     rf95.send((uint8_t*)msg, n);
-    rf95.waitPacketSent();
+    // NO waitPacketSent() here: it busy-waits for the whole time-on-air (159 ms at
+    // SF7/BW125 for an 88-byte frame) and loop() cannot sample while it spins. That
+    // blocking is what pulls 20 Hz sampling down to the measured 17.00 Hz, and at 5 Hz
+    // TX it would collapse sampling to ~4 Hz — below the 8 Hz abort floor and below
+    // what apogee::Confirm's 300 ms dwell needs. The guard above serialises transmits.
```

**API — VERIFIED against the installed RadioHead, not assumed.** Pinned version is
`mikem/RadioHead@1.120.0` (`firmware/platformio.ini`), confirmed `RH_VERSION_MAJOR 1` /
`RH_VERSION_MINOR 120` in `RadioHead.h:1419-1420`.

- **`isSending()` DOES NOT EXIST on `RH_RF95`.** It is defined only on `RH_NRF24`, `RH_NRF905`
  and `RH_NRF51`. Any design that reaches for it will not compile.
- **`mode()` is the correct equivalent and is public** — `RHGenericDriver.h:224`
  (`virtual RHMode mode();`, under the `public:` at line 43), returning `RHModeTx` while a
  transmit is in flight.
- **Completion is INTERRUPT-driven, so `mode()` is a genuine zero-cost poll.** `RH_RF95.cpp`
  `handleInterrupt()` has `else if (_mode == RHModeTx && irq_flags & RH_RF95_TX_DONE) { _txGood++;
  setModeIdle(); }`, and `setModeIdle()` sets `_mode = RHModeIdle` (`RH_RF95.cpp:392-398`).
  `_mode` is `volatile` (`RHGenericDriver.h:264`). The ISR is live on this board — `RFM95_INT`
  is pin 3 (`main.cpp:38`) and `rf95.init()` returns false if it is not a valid interrupt pin.
  **So the check costs no SPI traffic and no busy-wait.**
- `waitPacketSent(uint16_t timeout)` (`RHGenericDriver.h:123`) exists as a bounded fallback if a
  guard is unwanted, but it still spins. `mode()` is strictly better.

**Verdict: RadioHead makes this CLEAN on this driver, not awkward.** Two lines changed, no new
state machine, no library patch.

**What happens when the next TX tick arrives with a send still in flight — SKIP, and the
sub-decision matters more than the choice.**

| Option | Verdict |
|---|---|
| **Overwrite** | **Not available.** `RH_RF95::send()` opens with its own `waitPacketSent()`, so it cannot pre-empt; the only abort is `setModeIdle()`, which corrupts the frame in the air. Rejected. |
| **Queue** | **Rejected on merit.** Telemetry is a latest-value stream, not a reliable byte stream. A queued packet goes out carrying data that is already one period stale, and under sustained back-pressure the queue only ever grows staler. Also needs a buffer and a deferred-send state machine — real complexity for a worse answer. |
| **Skip** | **Correct.** Drop this tick; the next tick builds a **fresh** packet from the newest sample. Self-correcting, zero state. |

> **AND DO NOT INCREMENT `seq` ON A SKIP.**
> `seq` is incremented at `firmware/src/main.cpp:179`, immediately after the send. If a skipped
> tick burns a sequence number, the ground records it as a **lost packet** — and `SEQ` gaps are the
> sole input to `packets_lost` (`ground/flights/segmenter.py:184`) and the published `loss_pct`
> (`ground/publish/data.py:43`). A sled-side scheduling decision would be published as an RF-link
> statistic. **This is the same defect as §6.1's RX-loop overrun, on the other end of the link**, and
> it has the same fix: keep the two accountable separately. Count skips in a local `txSkipped` and
> print it beside `RATE:` so it is visible on the bench.

At the recommended 5 Hz (200 ms period) against a 194.82 ms worst-case ToA there are **5 ms of
margin**, so skips are not hypothetical — they will occur on wide frames. The behaviour must be
specified, not discovered.

**One hardening note the current code also needs.** `_mode` is cleared *only* by the ISR. If a
TxDone interrupt were ever missed, `mode()` would read `RHModeTx` forever and transmission would
stop permanently. **Today's code has the same failure mode and it is worse** —
`waitPacketSent()`'s `while (_mode == RHModeTx) YIELD;` is an unbounded loop, so a missed
interrupt hangs the sled outright rather than stalling TX. The guard should therefore carry a
watchdog: if `mode() == RHModeTx` for longer than ~2x the worst-case ToA (say 500 ms), call
`rf95.setModeIdle()` and count it. **This is a strict improvement on today regardless of the rate
change.**

**(b) State-dependent rate + landing cap — the actual feature (§5).**

```diff
-static const unsigned long TX_MS     = 1000;  // 1 Hz — DO NOT CHANGE without an ADR review
+// TX RATE IS STATE-DEPENDENT. 1 Hz on the pad; fast while in flight; back to 1 Hz after
+// FAST_WINDOW_S. The cap is NOT optional: launch::Confirm and apogee::Confirm both LATCH
+// permanently and there is no St:3 landed code (ADR 0001), so "fast while St != 0" would
+// never turn off — the sled would transmit at the flight rate until its battery died.
+static const unsigned long TX_PAD_MS      = 1000;   // 1 Hz on the pad
+static const unsigned long TX_FLIGHT_MS   = 200;    // 5 Hz in flight  <- the rate decision
+static const unsigned long FAST_WINDOW_MS = 60000;  // 3x the expected flight; then back to 1 Hz
@@  (TRANSMIT branch)
-  if (now - lastTxMs >= TX_MS && ...) {
+  const bool fastWindow = launchDet.is_in_flight() && (now - launchTime) < FAST_WINDOW_MS;
+  const unsigned long txPeriod = fastWindow ? TX_FLIGHT_MS : TX_PAD_MS;
+  if (now - lastTxMs >= txPeriod && ...) {
```

`TX_FLIGHT_MS = 200` (5 Hz) is the **maximum safe rate with no radio change**: it is under the
5.13 pkt/s worst-case ceiling (§3) and, with (a) applied, leaves sampling at ~20 Hz. It yields
**100 points per flight, 8 across the burn** — a 5x improvement, with zero RF-config risk.
Going beyond it requires the bandwidth change (§7 / M3).

### 9.2 Ground — required alongside

| Change | File | Why |
|---|---|---|
| **Re-express the pad-baseline window in seconds** | `ground/flights/baseline.py:16-17` (+ both `_HIST_LEN` sites) | **§6.5 — the one thing that BREAKS.** Guard with the F1 golden fixture; result must stay byte-identical. |
| Make the dashboard trace a time window; deque instead of tuple-slice | `ground/dashboard/model.py:52,71` | §6.6 — 5 min silently becomes 30 s |
| Shrink the RX idle sleep; add a distinct overrun counter | `ground/ingest/service.py:222` | §6.1 — otherwise receiver latency is published as RF loss |

### 9.3 Ground — required only if the bandwidth changes

| Change | File |
|---|---|
| `LoRaConfig(bandwidth_khz=500)` | `ground/ingest/service.py:118` |

### 9.4 Explicitly NOT changing

- **`RX_STALE_S` / `STALE_S`** (`ground/panel/supervisor.py:24-25`, `ground/oled/spec.py:37`) — §6.2.
- **The 90 s silence timeout** — §6.3.
- **`MET`'s units** — §6.7; that is a `V:2` bump for no gain.
- **ADR 0001** — nothing here changes the wire grammar or any tag's meaning. Rate is not part of
  the contract. **No version bump, no ADR amendment.** (The ADR's "negligible at 1 Hz" airtime
  remark at line 107 is now stale and should get a one-line footnote pointing here.)
- **`docs/RESUME.md`** — no agent writes it (parallel-agent rule 6). Two corrections are owed to it:
  the 107 → 113 byte figure (§2) and the 17 Hz attribution (§4).

---

## 10. Recommendation

**5 Hz in flight, 1 Hz on the pad, capped at 60 s after launch — with non-blocking TX, and the
pad-baseline window fixed first.**

- **5x the flight resolution** (20 → 100 points; 1.6 → 8 points across the burn).
- **No RF configuration change**, so no silent-cutover risk and no e2e re-gate beyond a normal bench run.
- **What limits it: the sled's blocking transmit, not the radio and not the law.** Once that is
  fixed, the binding limit is the 5.13 pkt/s worst-case airtime ceiling.
- **The prerequisite is ground-side:** §6.5. Shipping the rate change without it silently shortens
  the AGL baseline window 5x and can move the published peak altitude — the same class of defect as
  the 84 ft error the `max_is_meaningful` gate was written to fix.

**If 5 Hz proves insufficient after a real flight, the next step is bandwidth, not spreading factor:**
BW 500 kHz costs 6 dB of a ~73 dB margin and raises the ceiling to 20.5 pkt/s, making 10–20 Hz
available. **That is a second, separately-gated decision** — it is a coordinated both-ends cutover
whose failure mode is silent total link loss, and it should not ride along with the rate change.
