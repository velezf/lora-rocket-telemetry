# AGL baseline v2 — audit + plan

Read-only audit (per Frank's 4.5/baseline-v2 kickoff). Documents the V1 zeroing
algorithm, what survived the Epic-3 port, the flight-logic baseline-dependence,
and the proposed v2 ground-side design. **No firmware is touched in this work.**

## 1. V1 reference algorithm (`RocketLoRaTelemetry/Feather9x_TX/Feather9x_TX_V1.2.6.ino`)

- **BMP390 config** (setup): temp OS ×8, pressure OS ×4, **IIR filter coeff 3** — hardware
  noise smoothing before any software touches the reading.
- **Boot calibration** (lines 92–100): `groundPressure = arithmetic mean of 50 BMP pressure
  reads @ 50 ms = a 2.5 s boot average`. **Locks once**, before the flight loop; never recalibrates.
- **Altitude**: `altitudeFt = bmp.readAltitude(groundPressure) × 3.28084` — **boot-relative**.
- **The header's "Trimmed-mean baseline" is NOT implemented** — the code is a plain mean, no
  sort / trim / outlier reject. **No stability criteria, no variance gate, no re-lock.** Boot
  transient handling = IIR + oversampling + the 2.5 s averaging window, nothing more.

**So the "V1 stability/trimming" we remembered doesn't exist in the code.** The only borrowable
V1 value is the **window length (2.5 s)**; there is no variance threshold to inherit.

## 2. Current firmware (Epic-3 port)

- **Boot-zeroing survived the port intact**: identical 50-sample boot mean (`firmware/src/main.cpp:81–83`),
  identical BMP config (`77–79`). Raw ALT is **boot-relative** (not ASL).
- **The "boot noise"**: if the 2.5 s boot window catches the BMP power-on settling transient (or
  the sled is moved after boot), `groundPressure` is biased → the pad reads a nonzero offset.
  Measured on F1: pad ALT −85..−67 ft, stdev 3.71 ft over 9 min; short quiet windows 0–1.6 ft.
- **Real-world context (Frank):** the field is **~400–413 ft ASL**. Raw ALT is boot-relative, so
  the −77 ft pad readings are relative to boot, **not** ASL; the ~13 ft ASL spread Frank cites
  matches our measured baro noise — i.e. the pad was **static** and F1's "8 ft AGL peak" was
  sensor noise, not a climb (consistent with "swing, not flight"). Field elevation is a good
  candidate for a flight `--field` annotation, separate from the AGL zero.

## 3. Flight-logic baseline-dependence

- **Launch detect** — baseline-**independent** (accel `g` vs 3.0 only; no altitude).
- **Apogee detect** — baseline-**independent**: `apogee::Detector` tracks a relative running max
  and fires on the first drop below it. A constant altitude offset shifts every sample equally →
  same apogee sample, same descent latch.
- **Verdict: no flight LOGIC depends on the zero.** The baseline is a **display / record-quality**
  concern only. → **No firmware logic gap; no mandatory Epic 6 rider.** (Optional quality rider below.)

## 4. v2 ground-side design (this branch — pure unit, host-tested)

Replace the naive "rolling mean of all `St:0` ALT" with a **retrospective, stability-gated,
trailing-window baseline locked at `flight_open`** and stored in the flight record.

- **Baseline @ flight_open**: from the buffered pre-boost pad ALT, take a trailing low-variance
  window, **excluding the final ~2 s** (pre-boost handling / boost onset). Mean of that window = baseline.
- **Live path**: the sampler holds the candidate window continuously; **locks the instant
  flight_open fires**, holds through the flight, unlocks on `flight_close`. Display AGL unchanged
  otherwise; **raw ALT is still never transformed in records.**
- **Derive path**: the **same pure function** recomputes the baseline on rebuild; **baseline
  becomes part of the derived flight record** (`baseline_ft` + `baseline_window` in the index entry).
- **Fixtures**: boot-transient settling curve → excluded (high-variance early samples never enter
  the trailing window); carry-to-pad motion → excluded (fails the variance gate); long pad wait
  with slow drift → baseline tracks the **late quiet window**, not stale early drift; **F1 golden
  → recompute + report its baseline.**

### Parameters (accepted 2026-07-08)

| Param | Value | Source |
|---|---|---|
| Trailing window `N` | **15 samples (~15 s @ 1 Hz)** | V1's "short average just before use" (2.5 s @ 20 Hz) adapted to the ~1 Hz ground packet rate; 2.5 s ≈ 2–3 packets is too few for a variance estimate. |
| Pre-boost exclusion | **final 2 samples (~2 s)** | mirrors "exclude the final 1–2 s pre-boost". |
| Stability gate | **stdev ≤ 2.0 ft** over the window (else baseline = None → AGL falls back to raw) | **Data-derived from F1 pad** (quiet windows 0–1.6 ft; drift/motion 3.7 ft+). **V1 has no threshold to borrow** — flagged as new, not invented arbitrarily. |

**F1 recomputed:** from the 19 quiet pre-boost pad packets (SEQ 0–18, ALT −83..−85),
`baseline_ft = −84` over `n = 15` → peak AGL = −74 − (−84) = **10 ft** (sensor noise; a swing,
not a climb). Stored in the golden fixture's expected index entry.

## 5. Firmware boot-settling — NOTE only, not a rider (decided 2026-07-08)

Boot calibration can capture the BMP power-on settling transient → biased `groundPressure`. But
**the bias cancels in AGL**: both raw ALT and the pad baseline share the same boot-mean reference,
so `AGL = ALT − baseline` is unaffected by a constant boot offset. Ground v2 additionally excludes
the transient (trailing quiet window). **Cosmetic only (raw ALT display) — no flight-logic impact,
no AGL impact.** Deliberately **kept as this note, NOT an Epic 6 rider**; firmware stays untouched.
