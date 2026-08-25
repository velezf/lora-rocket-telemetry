/*
 * Sled TX firmware — ADR-0001 v1 telemetry (Epic 3 integration)
 *
 * Wires the merged, host-tested pure units into the TX loop:
 *   lib/convert  raw accel -> g, pressure -> altitude (ft)
 *   lib/launch   launch detection (g threshold)
 *   lib/apogee   apogee / descent detection
 *   lib/packet   ADR-0001 v1 packet encoder (all formatting lives here — no
 *                format strings scattered in src/)
 *
 * Hardware glue (Arduino / RadioHead / sensors) stays in src/; the pure logic
 * stays in lib/ and is host-tested via `pio test -e native`. This replaces the
 * legacy V1.2.6 string with the ADR v1 format: V:1 SYS:7 SRC:1 SEQ:.. St:.. ...
 *
 * Live-state wiring (Epic 3.3/3.4): SYS default 7, SRC 1=sled, SEQ per-TX
 * counter (wraps at 65535), St flight-state code (0 pad / 1 ascent / 2 descent),
 * MET seconds since launch.
 *
 * Hardware: Adafruit Feather M0 + RFM95 (RF params in lib/rfconfig/rf_config.h), BMP390 (I2C),
 *           ADXL375 (I2C).
 */
#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <RH_RF95.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP3XX.h>
#include <Adafruit_ADXL375.h>

#include <packet.h>
#include <txgate.h>
#include <sensor_health.h>
#include <launch_confirm.h>
#include <apogee_confirm.h>
#include <convert.h>
#include <velocity.h>
#include <envelope.h>
#include <rf_config.h>
#include <txsched.h>

// -------------------- Pins / radio --------------------
#define RFM95_CS    8
#define RFM95_RST   4
#define RFM95_INT   3
// RF link parameters live in rf_config.h (both-ends constants, ADR 0005) — not here.

static const unsigned int SYS_ID = 7;  // ADR default network id
static const unsigned int SRC_ID = 1;  // 1 = sled

// -------------------- Hardware / state --------------------
RH_RF95 rf95(RFM95_CS, RFM95_INT);
Adafruit_BMP3XX bmp;
Adafruit_ADXL375 adxl(0x53, &Wire);

// Confirmed launch: CONFIRM-OR-REVERT. The accel gate (3 g held 100 ms) only decides when to
// START watching altitude; the ALTITUDE GAIN is what declares the launch, and a provisional
// that never climbs reverts instead of latching forever. Measured on the profiles: a dwell
// separates a knock from a launch by a factor of two, altitude separates them by three orders
// of magnitude, so the dwell stays short and altitude does the rejecting. St:1 costs 531-944 ms
// of extra St:0 on the wire; MET zero is BACKDATED to the accel gate, so it is not delayed.
launch::Confirm launchDet;   // 3 g / 100 ms / 50 ft / 2000 ms / fallback 300 ms
// Confirmed apogee: hysteresis + dwell, so one noisy boost sample cannot latch St:2 for
// the whole flight and corrupt the flight record. Constants are in TIME, not samples.
apogee::Confirm apogeeDet(20.0f, 300);
// Non-blocking TX gate: SEND/SKIP/FORCE decisions are pure and host-tested (lib/txgate);
// only the mode() read and setModeIdle() stay here. 500 ms stuck bound (see txgate.h).
txgate::Gate txGate;
// Per-sensor read isolation: separate failure counters, time-based health (see
// sensor_health.h — including why the ADXL375 is deliberately not covered).
sensors::Health sensorHealth;
// Vel: onboard dh/dt at the sample rate, time-constant EMA (tau lives in velocity.h).
// Fed ONLY on good baro reads — a failed read widens dt instead of faking a sample.
velocity::Estimator velEst;
// Gmx/Gmn: min/max |g| across the TX window. Reset discipline is in envelope.h: reset
// ONLY when a frame actually goes to air, so a TX skip extends the window rather than
// losing a spike to scheduling.
envelope::Window gEnv;

float groundPressure = 1013.25f;  // hPa, calibrated at boot
float peakG = 0.0f;
unsigned int seq = 0;             // SEQ, wraps at 65535
unsigned long launchTime = 0;

float readBatteryVoltage() {
  int raw = analogRead(A7);  // A7 reads battery via a 2:1 divider
  return raw * 3.3f / 1023.0f * 2.0f;
}

void setup() {
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);
  Serial.begin(115200);
  unsigned long serialWait = millis();       // bounded wait -> runs headless
  while (!Serial && (millis() - serialWait) < 2000) delay(1);
  delay(100);

  digitalWrite(RFM95_RST, LOW); delay(10);
  digitalWrite(RFM95_RST, HIGH); delay(10);
  if (!rf95.init()) { Serial.println("LoRa init failed"); while (1); }
  rf95.setFrequency(rf::FREQ_HZ / 1e6f);
  // BW500 cutover (ADR 0005; step 6), hardened per red-team finding 1: the modem
  // registers are DERIVED from rf_config.h at compile time — no ModemConfigChoice
  // enum whose meaning lives in prose. Derivation mirrored from the ground station
  // and pinned by test_rfconfig; the cross-end test compares register semantics.
  RH_RF95::ModemConfig modem = { rf::MODEM_REG_1D, rf::MODEM_REG_1E, rf::MODEM_REG_26 };
  rf95.setModemRegisters(&modem);
  rf95.setPreambleLength(rf::PREAMBLE_LEN);
  // RadioHead never writes RegSyncWord; the SX127x powers on at 0x12 and the ground
  // writes 0x12 explicitly. Written here too so the sled's sync word is PROGRAMMED
  // from the shared constant, not assumed from power-on state.
  rf95.spiWrite(RH_RF95_REG_39_SYNC_WORD, rf::SYNC_WORD);
  rf95.setTxPower(rf::TX_POWER_DBM, false);

  if (!bmp.begin_I2C()) { Serial.println("BMP390 not found"); while (1); }
  // 1x oversampling, NOT temp-off: BMP3 pressure compensation REQUIRES the temperature
  // term (temp_en is set unconditionally inside performReading), so the sensor still
  // converts temperature once per reading — only the oversampling drops,
  // 16,323 us -> 2,183 us. The API name for 1x is BMP3_NO_OVERSAMPLING (0x00 = one
  // conversion, no extra samples) — "NO_OVERSAMPLING" does not mean "no temperature".
  //
  // JUSTIFICATION, CORRECTED (2026-08-07, two agents independently): this is NOT a
  // sample-rate fix. performReading() does not wait for the conversion, so the old 8x
  // setting was never the reason the loop ran at 17 Hz — waitPacketSent() was. This
  // change is the PRECONDITION for any tick below 25 ms of conversion latency, and its
  // effect on achieved rate is MEASURED at the bench, not assumed here.
  bmp.setTemperatureOversampling(BMP3_NO_OVERSAMPLING);
  bmp.setPressureOversampling(BMP3_OVERSAMPLING_4X);
  bmp.setIIRFilterCoeff(BMP3_IIR_FILTER_COEFF_3);

  float sum = 0;                              // trimmed ground-pressure baseline
  for (int i = 0; i < 50; i++) { bmp.performReading(); sum += bmp.pressure / 100.0f; delay(50); }
  groundPressure = sum / 50.0f;

  if (!adxl.begin()) { Serial.println("ADXL375 not found"); while (1); }
  Serial.println("Sled TX ready (ADR v1)");
}

// SAMPLE FAST, TRANSMIT SLOW (6.0a).
//
// Sampling and transmitting used to be the SAME loop, gated by delay(1000) — so the
// detectors saw one sample per second, which is why the 2026-07-08 shake test's 2.2 g jerk
// fell between samples and never tripped launch detection.
//
// THE WIRE HAS NOW CHANGED TOO (ADR 0005) — this note superseded the 6.0a-era "wire is
// unchanged" claim, which stopped being true on this branch: TX is St-dependent
// (lib/txsched), and the frame carries three additive tags (Vel/Gmx/Gmn). All of it
// within ADR 0001 v1 (additive tags, no bump); the ground decodes the new tags (merged
// with the newtag collision proof) and the e2e fixtures cover both frame shapes.
//
// Measured on the synthetic profile (firmware/lib/profile, 6.0b): confirmed-apogee latency
// costs 77.9 ft of altitude at 1 Hz versus 33.8 ft at 20 Hz. Most of that is won by 5 Hz
// (41.2 ft) — so if the BMP390 cannot sustain 20 Hz at the configured oversampling, a lower
// achieved rate degrades this gracefully rather than invalidating it.
static const unsigned long SAMPLE_MS = 50;    // 20 Hz target; ACHIEVED rate is reported below
// TX interval is NO LONGER A CONSTANT: 1 Hz pad / 10 Hz flight, MET-bounded — the
// ADR review the old "DO NOT CHANGE" note demanded is ADR 0005. Policy, rates and
// the fast-window bound live in lib/txsched/txsched.h (cited, not restated).

static unsigned long lastSampleMs = 0;
static unsigned long lastTxMs     = 0;
static float lastAltFt = 0.0f, lastTempC = 0.0f, lastG = 0.0f;

// Achieved-rate self-report: the BMP390's real throughput at our oversampling is a MEASURED
// property, not a chosen one. Counting and printing it means the number arrives with the
// build instead of gating it, and a shortfall is visible on the bench rather than inferred.
static unsigned long sampleCount = 0, sampleWindowStart = 0;
static unsigned long encodeFailures = 0;   // frames dropped LOUDLY by encode_packet

void loop() {
  const unsigned long now = millis();

  // ---- SAMPLE (fast) ----
  if (now - lastSampleMs >= SAMPLE_MS) {
    lastSampleMs = now;
    // A failed barometer read skips THIS SAMPLE ONLY. It used to `return` from the whole
    // loop, which also skipped the transmission — one bad I2C read cost a packet, and at
    // 20 Hz there are 20x more chances to hit it. One failure path must not take out an
    // unrelated responsibility.
    // baroOk is the launch detector's altitude-validity signal as well as the health
    // input: a read that did not answer must not look like "altitude is not climbing".
    const bool baroOk = bmp.performReading();
    sensorHealth.note(sensors::BARO, baroOk, now);
    if (baroOk) {
      lastAltFt  = pressure_to_altitude_ft(bmp.pressure / 100.0f, groundPressure);
      lastTempC  = bmp.temperature;
      sampleCount++;
      velEst.update(lastAltFt, now);
    }

    // The ADXL375 read has NO failure signal — getEvent() returns true unconditionally
    // (verified in the vendored driver), and zero-magnitude-as-failure would trip on a
    // coasting rocket at a legitimate ~0 g. Unmonitored BY DESIGN; see sensor_health.h.
    sensors_event_t e;
    adxl.getEvent(&e);
    lastG = accel_magnitude_g(e.acceleration.x, e.acceleration.y, e.acceleration.z);
    gEnv.note(lastG);   // every sample reaches the envelope; TX consumes it below

    // launch_ms() is BACKDATED to the accel gate, so the confirmation window buys robustness
    // without moving MET zero. Using `now` here would charge MET for the whole window.
    if (launchDet.update(lastG, lastAltFt, baroOk, now)) {
      launchTime = launchDet.launch_ms();
      Serial.print("LAUNCH confirmed, MET zero at "); Serial.print(launchTime);
      Serial.print(" ms, reverts "); Serial.print(launchDet.reverts());
      Serial.println(launchDet.used_fallback() ? ", ALTITUDE UNAVAILABLE (accel-only)" : "");
    }
    if (launchDet.is_in_flight()) {
      // Gate on baroOk, NOT on ever-having-sampled: apogee::Confirm's dwell is
      // TIME-based, so replaying a stale altitude with a fresh timestamp is live
      // evidence to it — a noise dip followed by a >=300 ms baro wedge would
      // confirm St:2 from a sensor that wasn't answering (red team, 2026-08-24).
      // A read that did not answer contributes NOTHING, same discipline as
      // velEst and launchDet above.
      if (baroOk) apogeeDet.update(lastAltFt, now);
      if (lastG > peakG) peakG = lastG;
    }
  }

  // ---- TRANSMIT (non-blocking; the sample loop no longer stops for the radio) ----
  if (now - lastTxMs >= txsched::interval_ms(launchDet.is_in_flight(), now, launchTime)) {
    lastTxMs = now;

    // The old path was send() + waitPacketSent(), which blocked the ONE thread this
    // firmware has for the whole time-on-air — measured at ~33 ms of every 59 ms sample
    // period at 1 Hz, and fatal at any higher TX rate. RadioHead's send() is async-start;
    // the gate (pure, host-tested) decides SEND / SKIP / FORCE from mode() alone.
    const txgate::Decision txd =
        txGate.update(rf95.mode() == RHGenericDriver::RHModeTx, now);

    if (txd == txgate::SKIP) {
      // Previous frame still on air. SEQ DOES NOT ADVANCE: a scheduling skip published
      // as a SEQ gap would be counted by the ground as RF loss (the SEQ-gap statistic is
      // the loss statistic), lying about the link. Fresh data goes at the next tick.
    } else {
      if (txd == txgate::FORCE_IDLE_SEND) {
        rf95.setModeIdle();   // missed TxDone: the old unbounded hang, now bounded+counted
      }

      const bool inFlight   = launchDet.is_in_flight();
      const bool descending = apogeeDet.is_descending();

      Packet p;
      p.sys    = SYS_ID;
      p.src    = SRC_ID;
      p.seq    = seq;
      p.state  = !inFlight ? 0u : (descending ? 2u : 1u);
      p.alt_ft = (int)lroundf(lastAltFt);
      p.max_ft = (int)lroundf(apogeeDet.max_altitude());   // 0 until first in-flight sample
      p.g      = lastG;
      p.pg     = peakG;
      p.temp_c = lastTempC;
      p.batt_v = readBatteryVoltage();
      p.met_s  = inFlight ? (unsigned int)((now - launchTime) / 1000UL) : 0u;
      p.vel_fps = velEst.vel_fps();
      p.gmx     = gEnv.gmx();
      p.gmn     = gEnv.gmn();

      // 256 B: TODAY's worst case is 141 B (12 tags + Vel/Gmx/Gmn — pinned by
      // test_worst_case_frame_is_141_bytes_per_adr0005). Wmx and the raw 9-DoF pad
      // tags are NOT yet emitted (no LSM6DSOX driver in src/), so A1.4's 210 B pad
      // frame is what this buffer is sized AHEAD for, under the 251 B
      // RH_RF95_MAX_MESSAGE_LEN send cap. If a range assumption grows, the A1.4
      // table and the pinned length move together or encode_packet returns 0 below.
      char msg[256];
      size_t n = encode_packet(p, msg, sizeof(msg));
      if (n == 0) {
        // encode_packet is LOUD on truncation: nothing is transmitted, the failure is
        // counted and printed, and SEQ still advances so the ground sees a SEQ gap
        // instead of silence it can misread as RF loss being absent.
        encodeFailures++;
        Serial.println("ENCODE OVERFLOW: frame dropped");
      } else {
        Serial.print("TX: "); Serial.println(msg);
        rf95.send((uint8_t*)msg, n);   // async-start; NO waitPacketSent — that was the
                                       // ~33 ms/sample the loop has been paying
        gEnv.reset();                  // the window's values are ON AIR — and only now:
                                       // an encode drop above keeps accumulating, so the
                                       // spike is not lost with the frame
      }
      seq = (seq + 1) & 0xFFFF;   // wrap at 65535 per ADR; NOT reached on SKIP
    }

    // Achieved sample rate over the last window — the measurement, printed with the build.
    if (sampleWindowStart == 0) sampleWindowStart = now;
    else if (now - sampleWindowStart >= 5000UL) {
      Serial.print("RATE: "); Serial.print(sampleCount * 1000.0f / (now - sampleWindowStart));
      Serial.print(" Hz achieved, baro failures "); Serial.print(sensorHealth.failures(sensors::BARO));
      // The time-based health verdict, CONSUMED (red-team finding 9: healthy() had no
      // caller — designed-but-inert). 0 here on the bench means the baro has not
      // answered within stale_ms even if the failure count looks small.
      Serial.print(", baro healthy "); Serial.print(sensorHealth.healthy(sensors::BARO, now) ? 1 : 0);
      // Reverts are transients the detector rejected. A non-zero count on the pad is the sled
      // telling you it was knocked -- and that it correctly declined to call it a launch.
      Serial.print(", launch reverts "); Serial.print(launchDet.reverts());
      Serial.print(", encode overflows "); Serial.print(encodeFailures);
      Serial.print(", tx skips "); Serial.print(txGate.skipped());
      Serial.print(", tx forced "); Serial.println(txGate.forced());
      sampleCount = 0; sampleWindowStart = now;
    }
  }
}
