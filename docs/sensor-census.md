# Sensor census — the sled, end to end

**Base commit `5642627` (branch `feat/sensor-census`).** Every claim below is relative to that
tree; anything committed only on another feature branch is invisible here.

**No hardware was touched to produce this.** Everything marked VERIFIED was verified against
source in this repository, against library source resolved by `pio`, or against a datasheet
formula that reproduces an independently-measured number. Everything else is labelled INFERRED
or ASSUMED, and §7 lists what only the bench can settle.

This document is the authority for **which sled sensor exists in which state**. It does not
restate literal addresses that live in code — it cites them. Ground-station peripherals are
[`ground-station-wiring.md`](ground-station-wiring.md)'s to state, not this file's.

---

## 1. The census

Six devices are candidates for the sled. Only two are read by the flight firmware.

| # | Device | Bus / address | Present? | Library (declared?) | Fields produced | Reaches the packet? |
|---|--------|---------------|----------|---------------------|-----------------|---------------------|
| 1 | **BMP390** barometer | I²C `0x77` (`bmp.begin_I2C()` default, `firmware/src/main.cpp`) | **YES** — flown | `adafruit/Adafruit BMP3XX Library` — **declared** | pressure, temperature | **YES** → `ALT`, `Max` (via `pressure_to_altitude_ft`), `T` |
| 2 | **ADXL375** ±200 g accel | I²C `0x53` (literal in `firmware/src/main.cpp`) | **YES** — flown | `adafruit/Adafruit ADXL375` — **declared** | accel x/y/z | **PARTLY** → magnitude only, as `G`/`Pg`. Per-axis is not transmitted on this branch |
| 3 | **LSM6DSOX** gyro + 16 g accel | I²C `0x6A` or `0x6B` (`LSM6DSOX_ADDRS`, `firmware/src/imu9dof.h`) | **PROBABLY** — see §2 | `adafruit/Adafruit LSM6DS` — **declared on this branch, was not before** | gyro x/y/z, accel x/y/z, die temp | **NO** — no tag exists. `Roll`/`Spin` are *reserved names only* (ADR 0001 App. A) |
| 4 | **LIS3MDL** magnetometer | I²C `0x1C` or `0x1E` (`LIS3MDL_ADDRS`, `firmware/src/imu9dof.h`) | **PROBABLY** — see §2 | `adafruit/Adafruit LIS3MDL` — **declared on this branch, was not before** | mag x/y/z | **NO** — no tag exists |
| 5 | **Battery sense** | ADC on pin `A7`, 2:1 divider (`readBatteryVoltage`, `firmware/src/main.cpp`) | **YES** — flown | none (`analogRead`) | cell volts | **YES** → `Batt` |
| 6 | **2× STEMMA relays** | — | in the parts bin | — | not a sensor | n/a — **unassigned** since deployment was dissolved (`PROJECT_PLAN.md` Epic 6) |

### Which packet fields have a live sensor behind them

Against the ADR 0001 v1 field table, all twelve tags:

| Tag | Backed by | Status |
|-----|-----------|--------|
| `V` `SYS` `SRC` | compile-time constants | **Constant.** `SYS_ID`/`SRC_ID` are literals; `SRC` per-unit build config is Epic 6.4, unbuilt |
| `SEQ` | firmware counter | Live |
| `St` | `launch::Confirm` + `apogee::Confirm` over BMP390 + ADXL375 | Live. **`St:3` (landed) does not exist** — Epic 6.3 |
| `ALT` `Max` | BMP390 | Live |
| `G` `Pg` | ADXL375 magnitude | Live |
| `T` | BMP390 | Live. **This is the only consumer of BMP390 temperature** — the altitude path never uses it (see §6) |
| `Batt` | A7 ADC | Live, **uncalibrated** (see §5.3) |
| `MET` | `millis()` since launch latch | Live |

**No packet field is a stub or a hardcoded placeholder.** The gap is the reverse shape: two
sensors that are physically present and produce nothing.

### What V1 had that V2 does not

Checked `RocketLoRaTelemetry/` (read-only) and `GroundStation/` including deleted history.

- **`Feather9x_TX_V1.2.6.ino` reads exactly the same two sensors** as V2 — BMP390, ADXL375, plus
  the A7 battery divider. **Nothing sled-side was dropped in the port.** VERIFIED.
- A third sketch, **`RocketLoRaTelemetry/radioRocketZwee/radioRocketZwee.ino`, was deleted** in
  `3498882` ("custom chip, not relevant to Feather M0 build"). It is a **Teensy** sketch
  (`BUILTIN_SDCARD`, `SCB_AIRCR`) that initialises **all six** parts — BMP390 (`begin_I2C(119)`,
  i.e. `0x77`), ADXL375, LSM6DSOX, LIS3MDL, BME680, APDS9960 — plus SD logging and ArduinoJson.
  It is **not** a V1 sled regression (it was never the sled firmware), but it is a **working
  reference init sequence** for the 9-DoF and it is the closest thing in history to a
  combined-sensor sketch. Its BME680 carries a hand-written comment that the part *"doesn't seem
  to want to work... even when it's the only connected device"* — **worth knowing before Epic
  7.2 blames its own code.**
- `GroundStation/` is a Node-RED flow and a readme. No sensors.

---

## 2. `0x6C` and `0x3D` — resolved: they are **not I²C addresses**

**They are WHO_AM_I register VALUES — device-identity bytes.** The confusion is understandable
because both happen to fall inside the 7-bit address range, and one of them collides with a real
address on a *different* machine.

### Evidence (VERIFIED — read out of library source, not recalled)

| Value | What it actually is | Where the constant is defined |
|-------|---------------------|-------------------------------|
| `0x6C` | **LSM6DSOX chip ID**, returned from register `0x0F` | `#define LSM6DSOX_CHIP_ID 0x6C ///< LSM6DSOX default device id from WHOAMI` — `Adafruit_LSM6DSOX.h` |
| `0x3D` | **LIS3MDL part ID**, returned from register `0x0F` | `if (chip_id.read() != 0x3D) { return false; }` — `Adafruit_LIS3MDL.cpp::_init()` |

The corresponding **I²C addresses** are different numbers entirely, also from those headers:
`LSM6DS_I2CADDR_DEFAULT 0x6A` and `LIS3MDL_I2CADDR_DEFAULT (0x1C)`.

Both constants were confirmed **twice, from independent copies**: the versions
`pio` resolves today, and the **vendored copies deleted in `c1b955c`**
("cleanup: remove vendored libraries"), recovered from history. They agree.

### Where the sketch went

There is **no combined 9-DoF sketch in this repository at any commit.** `git grep` across all
refs and `git log --all --diff-filter=D` return nothing but the two `docs/` references and the
vendored libraries. This confirms `epic5-integrity-note.md`: the 5.1 evidence came from an
uncommitted scratch sketch.

**But the likely source is recoverable.** `c1b955c` deleted the vendored
`Adafruit_LSM6DS/examples/adafruit_lsm6dsox_test/` and `Adafruit_LIS3MDL/examples/lis3mdl_demo/`
sketches. Those are exactly what a bench smoke test would have run, and they carry working init
sequences. `firmware/src/imu9dof.cpp` on this branch mirrors `lis3mdl_demo`'s configuration
(medium performance, continuous, 155 Hz, 4 gauss) and `radioRocketZwee`'s
`LSM6DS_ACCEL_RANGE_16_G` **deliberately**, so the new driver is continuous with whatever
produced the original reading rather than a fresh guess.

### ⚠ THE TRAP: `0x3D` IS ALSO A REAL ADDRESS, ON THE OTHER MACHINE

**The Pi 5 ground station's SSD1306 OLED sits at I²C address `0x3d`** — a different bus, a
different board, a different process. Two distinct facts share the number `0x3D`:

| | Machine | Bus | Meaning of `0x3D` |
|---|---|---|---|
| Sled | Feather M0 | sled STEMMA QT | **a WHO_AM_I value** returned by the LIS3MDL at address `0x1C` |
| Ground | Pi 5 `apogee-gs` | I²C-1 | **an address**, the OLED's — see `OLED_ADDR` in `ground/oled/display.py` |

They are unrelated. Do not let a bus scan on one be read as evidence about the other.

---

## 3. I²C scan request — for the main thread (the only party that may touch hardware)

Prior work was not reproducible because the probe was a scratch sketch with no SHA
(`epic5-integrity-note.md` §4, option B step 2). **This scan is therefore committed as a real
build artifact**, not pasted into a doc.

### Run it

```
cd firmware
git rev-parse HEAD                       # RECORD THIS — it identifies the binary
~/.platformio/penv/bin/pio run -e i2c_scan -t upload
~/.platformio/penv/bin/pio device monitor -e i2c_scan
```

Source: `firmware/tools/i2c_scan/i2c_scan.cpp`. The `[env:i2c_scan]` env builds **only** that
file — `main.cpp` is not linked, so the flight firmware is untouched by its existence
(verified: the `i2c_scan` build produces no `src/` objects at all). It is a separate binary,
so **re-flash the flight firmware afterwards.**

### What to send back — the whole serial dump, verbatim

One paste. It is a one-shot by design and answers all of the following in a single round-trip:

1. **Every ACKing address**, over `0x08`–`0x77`.
2. **Three passes per address**, reported as `n/3`. A device that answers 2/3 is a marginal
   pull-up or a loose QT connector — *present/absent alone would report that as a clean pass.*
3. **The identity-register value at every address a known part can occupy**, printed with the
   expected value beside it. An ACK proves only that *something* is there; `0x1C`/`0x1E`,
   `0x6A`/`0x6B` and `0x76`/`0x77` are each shared by more than one part.
4. **The same scan at 100 kHz and at 400 kHz.** A long STEMMA QT chain can pass at 100 kHz and
   fail at 400 — and 400 kHz is on the table as a cheap win (§6). Finding that out in flight is
   the expensive order.

### Decode table — every address you might plausibly see

Identity registers marked ✅ are probed automatically by the sketch.

| Addr | Most likely here | Other parts that use it | How to tell |
|------|------------------|-------------------------|-------------|
| `0x0C`/`0x0D` | — | AK8963 mag, MMC5603 | — |
| `0x18`/`0x19` | — | LIS3DH, LSM303 accel, MMA8451 | — |
| **`0x1C`** | **LIS3MDL** (SDO/SA1 low) — the sled's magnetometer | LSM303 accel `0x1C` variants | ✅ reg `0x0F` = `0x3D` |
| `0x1D` | ADXL375/343 with **ALT ADDRESS high** | MMA8451, LSM303AGR | ✅ reg `0x00` = `0xE5` |
| `0x1E` | **LIS3MDL** (SDO/SA1 **high**) — jumper moved | HMC5883L, LSM303DLHC mag | ✅ reg `0x0F` = `0x3D` |
| `0x29` | — | VL53L0X, TSL2591 | — |
| `0x39` | APDS9960 (lander, Epic 7) | — | ✅ reg `0x92` = `0xAB` |
| `0x3C`/`0x3D` | **SSD1306 OLED** | SH1106, SSD1305 | **No ID register — write-only.** If either ACKs on the *sled*, an OLED is on the sled bus; see §2's trap |
| `0x40` | — | INA219, Si7021, HTU21D | — |
| `0x48` | — | ADS1115, TMP102 | — |
| **`0x53`** | **ADXL375** (ALT ADDRESS low) — the sled's high-g accel | ADXL343 | ✅ reg `0x00` = `0xE5` |
| `0x57` | PiSugar battery (**Pi only**) | MAX3010x, 24Cxx EEPROM | — |
| `0x60` | — | MCP4725, Si5351, MPL3115A2 | — |
| `0x68` | PiSugar RTC (**Pi only**) | DS3231, PCF8523, MPU6050 | — |
| **`0x6A`** | **LSM6DSOX** (SDO/SA0 low) — the sled's 9-DoF | LSM6DS33/DSL/DSO32, ISM330 | ✅ reg `0x0F` = `0x6C` |
| `0x6B` | **LSM6DSOX** (SDO/SA0 **high**) | same family | ✅ reg `0x0F` = `0x6C` |
| `0x70` | — | TCA9548A mux, SHTC3 | If present, **devices may be hiding behind a mux** and a flat scan is incomplete |
| `0x76` | BMP390 with **SDO low** | BME280, BME680, BMP280 | ✅ reg `0x00` = `0x60` (BMP390) / `0x50` (BMP388); reg `0xD0` = `0x61` → BME680 |
| **`0x77`** | **BMP390** (SDO high) — the sled's barometer | BME680 default, BMP085/180 | ✅ same two probes |

**Expected clean result for the sled: exactly four addresses — `0x1C`, `0x53`, `0x6A`, `0x77`,**
all 3/3 at both speeds, all four identity probes matching.

**Anything else is a finding**, in particular: an address at 3/3 on 100 kHz but not 400 kHz
(bus integrity), `0x6B`/`0x1E` instead of `0x6A`/`0x1C` (a jumper, which would invalidate every
hardcoded-address assumption in the tree), or `0x70` (a mux).

---

## 4. Integration status — the 9-DoF is the only gap

### 4.1 What shipped on this branch

| Piece | File | Verified how |
|-------|------|--------------|
| Pure conversions + derivations | `firmware/lib/imu/imu.{h,cpp}` | **20 host tests**, `pio test -e native`, suite green at **54 cases** |
| I²C transport, address probe, WHO_AM_I | `firmware/src/imu9dof.{h,cpp}` | compiles into a real object referencing the real driver symbols (`nm` on `imu9dof.cpp.o`) |
| Library declaration | `firmware/platformio.ini` | **resolution**, not eyeballing — see 4.2 |
| Bus census tool | `firmware/tools/i2c_scan/`, `[env:i2c_scan]` | builds; links no `main.cpp` |
| Proposed loop integration | `docs/patches/0001-main-cpp-9dof.patch` | `git apply --check` passes; **the patched tree compiles** (built out-of-repo) |

The `lib/`/`src/` split is not ceremony here. **Every failure the pure layer can have is silent
in the data**: a wrong sensitivity constant yields a plausible roll rate, an unfolded tilt angle
yields a plausible attitude, a bias averaged over a bumped pad yields a plausible zero. None of
them raise. They have to be pinned on the ground, where they can still fail.

### 4.2 Library declaration — verified by RESOLUTION

This closes the "Epic 5's integrity hole" pattern: the previous build's dependence on ambient
state was real — the libraries were **absent from `lib_deps` entirely**, so nothing but a local
Arduino IDE install could have satisfied them.

Added to `[env:feather_m0_tx]`, version-pinned like every existing entry:
`adafruit/Adafruit LSM6DS@4.7.4`, `adafruit/Adafruit LIS3MDL@1.2.5`.

`~/.platformio/penv/bin/pio run -e feather_m0_tx`:

```
LDF: Library Dependency Finder -> https://bit.ly/configure-pio-ldf
LDF Modes: Finder ~ chain, Compatibility ~ soft
Found 24 compatible libraries
Scanning dependencies...
Dependency Graph
|-- RadioHead @ 1.120.0
|-- Adafruit BMP3XX Library @ 2.1.6
|-- Adafruit ADXL375 @ 1.1.2
|-- Adafruit Unified Sensor @ 1.1.15
|-- Adafruit LSM6DS @ 4.7.4
|-- Adafruit LIS3MDL @ 1.2.5
|-- SPI @ 1.0
|-- Wire @ 1.0
|-- apogee
|-- convert
|-- imu
|-- launch
|-- packet
...
RAM:   [==        ]  17.7% (used 5784 bytes from 32768 bytes)
Flash: [==        ]  21.7% (used 56844 bytes from 262144 bytes)
========================= [SUCCESS] Took 15.31 seconds =========================
```

`[env:native]` stays dependency-free; the `lib/` purity rule is intact — `firmware/lib/imu/`
includes only `<cmath>`.

**One trap worth naming.** Flash size did **not** change when `imu9dof.cpp` was added, because
nothing references it yet and the linker drops it. Size parity is therefore *not* evidence the
file compiled. It was verified the reliable way instead: `imu9dof.cpp.o` exists (2872 bytes) and
`nm` shows it referencing `Adafruit_LSM6DS::begin_I2C`, `Adafruit_LIS3MDL::read`, and the rest.

### 4.3 Addresses — probe, never hardcode

| Part | Address when select pin **low** | when **high** | Datasheet ID reg → value |
|------|--------------------------------|---------------|--------------------------|
| LSM6DSOX | `0x6A` (Adafruit breakout default) | `0x6B` | `0x0F` → `0x6C` |
| LIS3MDL | `0x1C` (Adafruit breakout default) | `0x1E` | `0x0F` → `0x3D` |
| ADXL375 | `0x53` (ALT ADDRESS low) | `0x1D` | `0x00` → `0xE5` |
| BMP390 | `0x76` (SDO low) | `0x77` (Adafruit default) | `0x00` → `0x60` |

`imu9dof::Sled9Dof::begin()` **tries both candidates for each part** and reports which answered.
Two reasons, and the second is the one that matters:

1. A jumper change or a different breakout revision becomes a recovered condition instead of
   "sensor not found".
2. **A hardcoded address cannot distinguish "absent" from "present at the other address."** The
   integrity note already flags this as the undetectable regression: if the LIS3MDL were on
   `0x1E`, nothing in the repo would notice.

The Adafruit `begin_I2C` verifies WHO_AM_I internally and returns false on mismatch, so a
foreign device ACKing at the same address is **rejected rather than driven**. VERIFIED in
`Adafruit_LIS3MDL.cpp` (`chip_id.read() != 0x3D`).

**The two currently-flown sensors still hardcode.** `Adafruit_ADXL375 adxl(0x53, &Wire)` and
`bmp.begin_I2C()` (default `0x77`) are literals. Not changed here — that is `main.cpp`, another
stream's file — but it is the same latent gap and worth a follow-up.

### 4.4 Calibration — three procedures, stated

#### (a) Gyro zero-rate offset — **required**, or roll data is wrong from the first sample

- **What is measured:** the three gyro outputs while the vehicle is *completely still*.
- **Against what reference:** stillness itself. No external instrument is needed — a MEMS gyro's
  true rate at rest is exactly zero, so the reference is the physics, not a standard.
- **How the constant is derived:** mean of N samples, via `imu::BiasAccumulator`.
  `add_if_still(x, y, z, gate)` **rejects** any sample whose components exceed `gate` (5 dps in
  the proposed patch), so a bumped pad is refused rather than averaged in. 200 samples at 5 ms
  ≈ 1 s of stillness.
- **Where it is stored:** in RAM, re-measured at every boot in `setup()`. Deliberate — the offset
  drifts with temperature and with time, so a value committed to the repo would be *stale in a
  way nobody could see*. The pad is the right place to take it.
- **How a wrong calibration shows up:** as a **constant non-zero roll rate on the pad**, which
  integrates into an ever-growing attitude error. This is the diagnostic: `Roll` should read ~0
  while the rocket is sitting on the rail. If it does not, the bias was taken while something
  moved. The firmware prints the bias and its accepted sample count at boot precisely so this is
  checkable before launch rather than inferred from a flight.

#### (b) Magnetometer hard-iron offset — **deferred, and say so**

- **What it would be:** the constant field offset contributed by the sled's own magnets, the
  LiPo, and the ferrous fasteners near the LIS3MDL.
- **Procedure:** rotate the assembled sled slowly through all orientations while logging mag
  x/y/z; the point cloud is a sphere displaced from the origin. The offset is the centre;
  soft-iron correction is the ellipsoid fit, which is a bigger job.
- **How a wrong one shows up:** heading error that varies with attitude — largest exactly when
  the rocket is tilted, i.e. when the number is being asked for.
- **Status: NOT DONE, and it is a real precondition for any heading claim.** The proposed patch
  therefore derives **roll rate from the gyro only** and makes no heading claim. Recording that
  as a deliberate scope limit rather than an oversight.

#### (c) `Batt` — **currently uncalibrated, and the divider ratio is assumed**

`readBatteryVoltage()` computes `raw * 3.3 / 1023 * 2.0`. Three assumptions are baked in and
none is measured: the 3.3 V rail is *exactly* 3.3 V, the SAMD21 ADC is 10-bit (it can be
configured to 12), and the divider is *exactly* 2:1. Procedure to fix: measure the cell with a
DMM at three states of charge, read the raw ADC at each, fit a linear scale. A wrong constant
shows up as a **go/no-go decision made on a wrong voltage** — which is exactly what the proposed
`BAT` tag (Epic 6.7) would be built on. Worth doing *before* that tag, not after.

---

## 5. Loop timing — the measured 17.00 Hz, verified and re-attributed

### 5.1 The stated breakdown is arithmetically right and causally wrong

`RESUME.md` records: *"BMP390 conversion is ~25 ms at the configured oversampling, of which
16.3 ms is 8x TEMPERATURE oversampling that altitude does not use, plus the ADXL I2C read each
tick ≈ 59 ms per sample."*

**The two BMP390 numbers reproduce exactly** from the BMP3xx datasheet conversion-time formula

```
t = 234 µs + press_en·(392 µs + 2^osr_p · 2020 µs) + temp_en·(163 µs + 2^osr_t · 2020 µs)
```

against the configured `BMP3_OVERSAMPLING_4X` pressure / `BMP3_OVERSAMPLING_8X` temperature:

| term | arithmetic | µs |
|------|-----------|-----|
| base | — | 234 |
| pressure, 4× | 392 + 4 × 2020 | 8 472 |
| temperature, 8× | 163 + 8 × 2020 | **16 323** |
| **total** | | **25 029 µs = 25.03 ms** |

So "~25 ms" and "16.3 ms" are both **CONFIRMED**. What does not follow is `25 + ADXL ≈ 59`.
25.03 ms plus an ADXL read (measured below at ~1.35 ms of bus time) is ~26 ms, not 59 ms. The
sum was never checked, and **the missing 33 ms is not in the sensors at all.**

### 5.2 The BMP390 conversion is not in the critical path — REFUTED

VERIFIED by reading the resolved library source:

- `Adafruit_BMP3XX::performReading()` writes the settings, calls `bmp3_set_op_mode()` to enter
  **forced** mode, then calls `bmp3_get_sensor_data()` **immediately**.
- `bmp3_get_sensor_data()` (`bmp3.c`) does exactly one thing: `bmp3_get_regs(BMP3_REG_DATA, …)`,
  parse, compensate. **There is no data-ready poll and no delay.**
- The only delay on the path is 5 ms inside `bmp3_set_op_mode()`, and it is skipped when the
  device is already in sleep — which it is, because forced mode self-clears to sleep after each
  conversion (INFERRED from the datasheet's forced-mode description; not verified from a
  datasheet I can read here).

**So `performReading()` costs I²C traffic, not 25 ms.** The 25 ms conversion runs in the sensor,
concurrently with the loop, and completes long before the next 50 ms tick.

Two consequences, and the second is the answer to the question that was asked:

- **The pressure value read at tick N is the conversion triggered at tick N−1.** Sequentially
  the BMP3 measures temperature then pressure, so with 8× temp the pressure sub-measurement
  falls roughly 16–25 ms into a conversion that started ~46 ms earlier — **the reading is
  ~21–29 ms old at the moment it is used.** At 300 ft/s that is ~7–9 ft of altitude lag. It is
  systematic, it biases the altitude *timeline* late by about half a tick, and it does **not**
  affect `Max` (a peak is a peak whenever it is sampled). Modest, but it should be known rather
  than discovered.
- **Dropping temperature oversampling buys back nothing in loop time.** See §6.

### 5.3 What actually costs the 3 Hz: the 1 Hz transmission blocks the loop

`rf95.send()` is followed by `rf95.waitPacketSent()`, which is `while (_mode == RHModeTx) YIELD;`
— **a busy wait**. Nothing is sampled during it.

`rf95.init()` selects `Bw125Cr45Sf128` (SF7 / BW 125 kHz / CR 4-5) and `setPreambleLength(8)`;
`RH_RF95_HEADER_LEN` is 4. All VERIFIED in `RH_RF95.cpp`/`.h`. Standard LoRa time-on-air for an
88-byte packet plus the 4-byte RadioHead header:

```
T_sym      = 2^7 / 125000                                    = 1.024 ms
T_preamble = (8 + 4.25) × 1.024                              = 12.544 ms
n_payload  = 8 + ceil((8·92 − 4·7 + 28 + 16) / (4·7)) × 5
           = 8 + ceil(752/28) × 5 = 8 + 27 × 5               = 143 symbols
T_payload  = 143 × 1.024                                     = 146.432 ms
T_air                                                        = 158.98 ms
```

**Every second, ~159 ms of the loop is spent blocked in `waitPacketSent()`.** That leaves
~841 ms for a 50 ms sample tick → 16.8 ticks, and because `lastSampleMs = now` re-phases the
schedule after the block, the loop fires one sample immediately on resume: **17 per second.**

A simulation of the exact loop structure gives **17.02 Hz** against the measured **17.00 Hz**,
and — the decisive part — **the result is unchanged whether the per-tick work is 2 ms, 6 ms or
26 ms.** The sensors are not the limiter. Setting the TX block to zero in the same simulation
yields **19.99 Hz**: the entire 20 → 17 shortfall is the radio.

### 5.4 Per-read costs

I²C on the SAMD21 runs at the Arduino default **100 kHz** — `Adafruit_I2CDevice::begin()` calls
`_wire->begin()` and never calls `setClock()` (VERIFIED). One byte = 9 bits = **90 µs**; a
register read of N bytes puts `3 + N` bytes on the wire.

| Read | Transaction shape | Bus time @100 kHz |
|------|-------------------|-------------------|
| ADXL375 `getEvent()` | **three** separate 2-byte reads (`getX`/`getY`/`getZ`) | 3 × 0.45 = **1.35 ms** |
| ADXL375 `getXYZ()` (unused) | one 6-byte burst | **0.81 ms** |
| LSM6DSOX `getEvent()` | one 14-byte burst (temp+gyro+accel) | **1.53 ms** |
| LIS3MDL `read()` | one 6-byte burst | **0.81 ms** |
| BMP390 `performReading()` | ~8–12 short transactions (settings + mode + 6-byte data) | **≈5 ms — ESTIMATED, not counted** |

Two findings fall out of that table:

- **`Adafruit_ADXL375::getEvent()` reads the three axes in three separate transactions.** Beyond
  costing 0.54 ms more than the burst, **X, Y and Z are sampled ~0.45 ms apart**, so the
  magnitude fed to launch detection mixes three instants. Irrelevant at 1 g; under high jerk it
  is a small real error. `getXYZ()` fixes both and is already in the library.
- The BMP390 figure is the **only estimated number in this section**, and §7 says how to
  measure it.

### 5.5 THE MENU — cost of each candidate, and the resulting rate

Baseline per-tick work taken as **6.35 ms** (ADXL 1.35 + BMP390 ~5.0). Rates are from the loop
simulation, with T_air = 158.98 ms.

| Option | Added ms/sample | Work/tick | Achieved | ms/sample | Verdict |
|--------|-----------------|-----------|----------|-----------|---------|
| **BASELINE (as flown)** | — | 6.35 | **17.02 Hz** | 58.8 | matches the measured 17.00 |
| + LSM6DSOX gyro+accel | **+1.53** | 7.88 | **17.02 Hz** | 58.8 | **free** |
| + LIS3MDL magnetometer | **+0.81** | 7.16 | **17.02 Hz** | 58.8 | **free** |
| **+ both 9-DoF parts** | **+2.34** | 8.69 | **17.02 Hz** | 58.8 | **free** |
| + both + Madgwick MARG fusion | +2.34 **+~1.0 est** | 9.69 | **17.02 Hz** | 58.8 | free — but see the caveat below |
| + both, at I²C 400 kHz | +0.58 | 6.93 | **17.02 Hz** | 58.8 | free; buys margin, not rate |
| ADXL `getEvent` → `getXYZ` | **−0.54** | 5.81 | **17.02 Hz** | 58.8 | free saving + removes axis tearing |
| + both, **and three more** hypothetical 6-byte sensors | +4.77 | 11.12 | **17.02 Hz** | 58.8 | still free |
| hypothetical **+45 ms** of work | +45 | 51.35 | 16.48 Hz | 60.7 | the cliff edge |
| hypothetical **+95 ms** of work | +95 | 101.35 | **8.41 Hz** | 118.9 | ⚠ **below the 8 Hz abort floor** |

**Read the shape, not the rows.** The tick is a 50 ms timer, and work below 50 ms is absorbed by
it entirely — the sample period stays exactly 50 ms whether the work is 2 ms or 45 ms. So:

> **There is ~43 ms of unused headroom per tick. Every sensor on the shopping list costs single-
> digit milliseconds. Adding all of them changes the achieved rate by nothing.**
>
> The rate does not degrade gradually — it is flat to ~44 ms of added work and then falls off a
> cliff. Nothing proposed comes within an order of magnitude of that cliff.

**Levers that DO change the rate** (none is a sensor):

| Change | Achieved | Note |
|--------|----------|------|
| `SAMPLE_MS` 50 → 25, with both 9-DoF parts | **34.04 Hz** | work is 8.69 ms, still far under a 25 ms tick |
| `SAMPLE_MS` 50 → 20, with both 9-DoF parts | **42.69 Hz** | ditto under a 20 ms tick |
| **Non-blocking TX** (drop `waitPacketSent`, poll instead) | **19.99 Hz** | recovers the full 20 Hz target at the current tick |
| Adding `Ax`/`Ay`/`Az` → 101-byte payload | **17.02 Hz** | +13 bytes ≈ +15 ms of air time; absorbed by the quantisation |

⚠ **`SAMPLE_MS` below ~25 ms would need the BMP390 reconfigured**: a 25 ms conversion cannot
sustain a 25 ms tick, and the loop would silently re-read the same conversion. *That* is where
dropping temperature oversampling earns its keep — see §6. Raising the sample rate is a
different decision from adding sensors and should not be smuggled in with one.

**Caveat on the fusion row (ASSUMED, not verified).** The SAMD21 is a Cortex-M0+ with **no
hardware FPU** — every float operation is a soft-float library call. ~1 ms for a Madgwick MARG
update plus Euler extraction is an estimate from operation counts, not a measurement, and it
could plausibly be 3–5× that. It still would not reach the cliff, but **do not treat it as
measured**; §7 says how to settle it.

---

## 6. The temperature-oversampling win — **REFUTED as stated, salvageable as a different claim**

The backlog item says dropping BMP390 temperature oversampling from 8× *"buys back most of the
sample-rate budget and is close to free."*

**It buys back no sample rate at all**, for two independent reasons, either of which is
sufficient:

1. **The conversion is not blocking** (§5.2). Time the sensor spends converting is time the loop
   spends doing something else. Removing sensor-internal time from a path the loop does not wait
   on changes nothing the loop can observe.
2. **Even if it were blocking, it is under the tick.** The tick is 50 ms and the whole
   conversion is 25.03 ms. The simulation confirms it directly: 26 ms of per-tick work and 6 ms
   of per-tick work both produce 17.02 Hz.

**And the saving is smaller than stated.** The claim is "16.3 ms". 16.323 ms is the *entire*
temperature term, but temperature **cannot be switched off**: BMP3 pressure compensation is a
function of compensated temperature, and `Adafruit_BMP3XX::performReading()` sets
`the_sensor.settings.temp_en = BMP3_ENABLE` **unconditionally** — VERIFIED in source, there is
no code path that disables it. Only the oversampling can drop:

```
temperature term, 8×  = 163 + 8 × 2020  = 16 323 µs
temperature term, 1×  = 163 + 1 × 2020  =  2 183 µs
saving                                  = 14 140 µs = 14.14 ms   (not 16.3)
total conversion 25.03 ms → 10.89 ms
```

**Nor does it improve freshness — if anything it slightly worsens it.** Because the read happens
on a fixed 50 ms schedule, finishing the conversion *earlier* means the completed value sits
*longer* before being read. With 8× temp the pressure sub-measurement lands ~21–29 ms before the
read; at 1× it lands ~35–44 ms before. INFERRED from the datasheet's temperature-then-pressure
ordering.

### What the change IS worth doing for

Three real reasons remain, and they should be the stated justification instead:

1. **It is the precondition for `SAMPLE_MS` < 25 ms.** A 10.89 ms conversion sustains a 20 ms
   tick (50 Hz); a 25.03 ms one does not. If the sample rate is ever raised, this stops being
   optional — and per §5.5 raising the tick is the only thing that raises the rate.
2. **Power.** Less than half the conversion duty cycle, at zero cost to `ALT`.
3. **`T` gets noisier and nothing else changes.** Its only consumer is the `T` telemetry tag —
   ambient air temperature, where 8× oversampling is not buying anything anyone reads.

**Recommendation: make the change, and change the reason.** It is close to free and it removes a
future blocker. It is not a sample-rate fix, and leaving that justification in the backlog would
mean the next person measures no improvement and concludes something is broken.

---

## 6b. Packet budget for gyro + mag — the 128-byte buffer overflows, and the failure is SILENT

**`char msg[128]` is a literal in `firmware/src/main.cpp:172`.** (`PACKET_BUF_LEN` does **not**
exist at this base commit — it is on the increment-2 branch only.) Current measured worst case
is **107 bytes**.

### Encoded cost of a tag

`1 (space) + len(name) + 1 (colon) + len(value)`. Worst-case values follow from the configured
full scales: gyro ±2000 dps → 32767 × 0.070 = **2293.7 dps** → `-2293.7`, 7 chars. Mag ±4 gauss
→ 32767 / 6842 × 100 = **478.9 µT** → `-478.9`, 6 chars.

| Option | Tags | Arithmetic | Added bytes | New worst case | vs 128 |
|--------|------|-----------|-------------|----------------|--------|
| **A** ADR-reserved only | `Roll` `Spin` | (1+4+1+7) + (1+4+1+4) = 13 + 10 | **+23** | **130** | ❌ **overflows by 2** |
| **B** 3-axis gyro | `Gx` `Gy` `Gz` | 3 × (1+2+1+7) = 3 × 11 | **+33** | **140** | ❌ overflows |
| **C** gyro + mag | + `Mx` `My` `Mz` | 33 + 3 × (1+2+1+6) = 33 + 30 | **+63** | **170** | ❌ overflows |
| **D** everything | A + C | 23 + 63 | **+86** | **193** | ❌ overflows |
| **C on top of increment-2's `Ax/Ay/Az`** | | 143 + 63 | +63 | **206** | ❌ also over 160 |

**Even the minimal, already-reserved `Roll`+`Spin` pair overflows the 128-byte buffer by 2
bytes.** Every option does.

- `160` (increment-2's `PACKET_BUF_LEN`) covers **A and B only** — not C, not D.
- **C needs 176; D needs 208; C-with-`Ax/Ay/Az` needs 224.**
- **The hard ceiling is 251, not "whatever we pick":** `RH_RF95_MAX_MESSAGE_LEN` = 251
  (`RH_RF95_FIFO_SIZE 255` − `RH_RF95_HEADER_LEN 4`).

### The encoder is safe. The wire is not.

`encode_packet` uses `snprintf` bounded by `out_len` and, on truncation, returns `out_len - 1` —
the bytes actually written. **VERIFIED: there is no buffer overrun and the returned length is
honest.** The memory safety is fine.

**But the frame that goes out is a silently truncated one, and the ground accepts most of them.**
Tested against the repo's own decoder (`ground/decode/v1.py`), truncating the golden packet one
byte at a time from the right:

```
  len  90  DecodedPacket   MET=6553      <<< ACCEPTED, MET WRONG, no error raised
  len  89  DecodedPacket   MET=655       <<< ACCEPTED, MET WRONG
  len  88  DecodedPacket   MET=65        <<< ACCEPTED, MET WRONG
  len  87  DecodedPacket   MET=6         <<< ACCEPTED, MET WRONG
  len  86..83  DecodeError  malformed-token
  len  82..78  DecodedPacket   MET=<ABSENT>  <<< ACCEPTED, MET silently missing
```

**9 of 13 truncation points produce a frame the ground accepts without moving any counter.**
Four carry a *well-formed but wrong* `MET` (65535 read as 6); five carry `MET` silently absent,
which ADR 0001 explicitly declares legal ("tolerate absent tags"). Only four raise
`malformed-token`.

**This is a data-integrity defect, not a robustness nit.** The LoRa CRC passes, the decoder
passes, no `errors` or `anomalies` counter moves, and the value in the flight record is wrong.
It is the same shape as the named failure class — *a check that looked like it was checking*.

### What follows

1. **`msg[]` must grow before any gyro/mag tag ships** — to 176 (option C) or 208 (option D),
   and it should become a named constant with a regression test, exactly as increment-2 did.
2. **Cap it at 252, never above.** `RH_RF95::send()` returns `false` and **transmits nothing**
   when `len > 251`, and `main.cpp:176` ignores that return — a silent no-transmit. Worse, its
   `len` parameter is `uint8_t`: a buffer above 256 could wrap a 260-byte length to 4 and send a
   4-byte frame.
3. **Append new tags LAST.** `snprintf` truncates from the right, so whatever is last is what is
   lost. Science tags at the end means a boost that overruns the buffer costs the roll rate, not
   `ALT`.
4. **The real fix is a length assertion at the encoder**, so an over-long packet is a loud
   failure on the bench rather than a quiet one in the flight record. Flagged, not built — it is
   `packet.*` and `main.cpp`, which belong to the firmware stream.

---

## 7. What could not be determined without hardware

Ordered by how much rests on it.

1. **Whether the LSM6DSOX and LIS3MDL are on the bus *now*, and at which addresses.** The only
   evidence is a status line whose artifact does not exist (`epic5-integrity-note.md`). §3's scan
   is the one-shot that settles it. **This is why the census says PROBABLY, not YES.**
2. **The BMP390's real `performReading()` cost.** Estimated at ~5 ms by counting transactions;
   never measured. The proposed patch adds `micros()` instrumentation to the sample tick and
   prints avg/max per-tick microseconds on the existing `RATE:` line — **the number nobody
   currently has.** The achieved-rate counter cannot supply it: with a 50 ms tick it reads
   exactly 20 Hz for any work under 50 ms, so it is flat right up to the cliff.
3. **Whether the bus survives 400 kHz** with the full QT chain. §3 scans at both speeds.
4. **The soft-float cost of a fusion update** on the M0+. Measure with the same tick
   instrumentation once the 9-DoF read is wired.
5. **The mounting axis.** `LONG_AXIS` in the proposed patch is a guess. Nothing in the data
   reveals a wrong choice — a mis-set axis reports a different, entirely plausible roll rate.
   It must be read off the physical sled.
6. **Magnetometer hard-iron offset** (§4.4b) — needs the assembled sled rotated through all
   orientations.
7. **The `Batt` divider ratio and ADC reference** (§4.4c) — needs a DMM.
8. **Whether the forced-mode power register really self-clears to sleep** (§5.2). If it does not,
   every `performReading()` pays an extra 5 ms. Either way the conclusion holds — 5 ms is not
   25 ms and both are under the tick — but the tick instrumentation would show it.

---

## 8. Not done here, and why

- **`firmware/src/main.cpp` is untouched.** Firmware is a single stream and `main.cpp` cannot
  have two owners. The integration is `docs/patches/0001-main-cpp-9dof.patch`, unapplied.
  Verified to apply cleanly (`git apply --check`) and to **compile** (built from an out-of-repo
  copy: flash 56 844 → 61 932 bytes, +5 088; RAM 5 784 → 5 960, +176).
- **No new packet tags.** `Roll`/`Spin` are reserved *names* in ADR 0001 Appendix A, not
  normative rows. Adding them is Epic 5.3, needs an ADR edit first, and must re-check the byte
  budget against `PACKET_BUF_LEN`. The proposed patch reports roll rate over **serial only**, so
  the wire contract is untouched and the e2e golden fixture stays valid.
- **No fusion.** `imu::tilt_off_axis_deg` is an accelerometer-only tilt, valid when the vehicle
  is quasi-static — i.e. **on the pad**, which is where "angle off vertical" is actually asked.
  Under boost it is meaningless, and calling it attitude would be an overclaim of exactly the
  kind `epic5-integrity-note.md` exists to stop. Real in-flight attitude needs Madgwick/Mahony
  plus the hard-iron calibration in §4.4b — Epic 5.2.
