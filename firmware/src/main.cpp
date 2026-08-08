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
 * Hardware: Adafruit Feather M0 + RFM95 (434 MHz, 23 dBm), BMP390 (I2C),
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
#include <launch_confirm.h>
#include <apogee_confirm.h>
#include <convert.h>

// -------------------- Pins / radio --------------------
#define RFM95_CS    8
#define RFM95_RST   4
#define RFM95_INT   3
#define RF95_FREQ   434.0  // MHz

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
  rf95.setFrequency(RF95_FREQ);
  rf95.setTxPower(23, false);

  if (!bmp.begin_I2C()) { Serial.println("BMP390 not found"); while (1); }
  bmp.setTemperatureOversampling(BMP3_OVERSAMPLING_8X);
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
// THE WIRE IS UNCHANGED. TX stays at exactly 1 Hz and the packet format is untouched, so the
// ground station needs no change, ADR 0001 needs no bump, and the e2e golden fixture stays
// valid. Only the DETECTORS and the onboard running Max see the faster rate.
//
// Measured on the synthetic profile (firmware/lib/profile, 6.0b): confirmed-apogee latency
// costs 77.9 ft of altitude at 1 Hz versus 33.8 ft at 20 Hz. Most of that is won by 5 Hz
// (41.2 ft) — so if the BMP390 cannot sustain 20 Hz at the configured oversampling, a lower
// achieved rate degrades this gracefully rather than invalidating it.
static const unsigned long SAMPLE_MS = 50;    // 20 Hz target; ACHIEVED rate is reported below
static const unsigned long TX_MS     = 1000;  // 1 Hz — DO NOT CHANGE without an ADR review

static unsigned long lastSampleMs = 0;
static unsigned long lastTxMs     = 0;
static float lastAltFt = 0.0f, lastTempC = 0.0f, lastG = 0.0f;
static bool  haveSample = false;

// Achieved-rate self-report: the BMP390's real throughput at our oversampling is a MEASURED
// property, not a chosen one. Counting and printing it means the number arrives with the
// build instead of gating it, and a shortfall is visible on the bench rather than inferred.
static unsigned long sampleCount = 0, sampleWindowStart = 0, baroFailures = 0;
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
    // baroOk is the launch detector's altitude-validity signal as well as the failure counter:
    // a read that did not answer must not be allowed to look like "altitude is not climbing".
    const bool baroOk = bmp.performReading();
    if (baroOk) {
      lastAltFt  = pressure_to_altitude_ft(bmp.pressure / 100.0f, groundPressure);
      lastTempC  = bmp.temperature;
      haveSample = true;
      sampleCount++;
    } else {
      baroFailures++;
    }

    sensors_event_t e;
    adxl.getEvent(&e);
    lastG = accel_magnitude_g(e.acceleration.x, e.acceleration.y, e.acceleration.z);

    // launch_ms() is BACKDATED to the accel gate, so the confirmation window buys robustness
    // without moving MET zero. Using `now` here would charge MET for the whole window.
    if (launchDet.update(lastG, lastAltFt, baroOk, now)) {
      launchTime = launchDet.launch_ms();
      Serial.print("LAUNCH confirmed, MET zero at "); Serial.print(launchTime);
      Serial.print(" ms, reverts "); Serial.print(launchDet.reverts());
      Serial.println(launchDet.used_fallback() ? ", ALTITUDE UNAVAILABLE (accel-only)" : "");
    }
    if (launchDet.is_in_flight()) {
      if (haveSample) apogeeDet.update(lastAltFt, now);
      if (lastG > peakG) peakG = lastG;
    }
  }

  // ---- TRANSMIT (slow, unchanged) ----
  if (now - lastTxMs >= TX_MS) {
    lastTxMs = now;
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

    // 256 B: sized to the LARGEST frame of the E+F split (ADR 0005 A1.4) — the 210 B
    // worst-case PAD frame (12 tags + Vel/Gmx/Gmn + raw 9-DoF), not the 152 B flight
    // frame — under the 251 B RH_RF95_MAX_MESSAGE_LEN send cap. Range assumptions
    // behind those worst cases live in the A1.4 table; if a field's range grows, the
    // table and this size move together or encode_packet starts returning 0 below.
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
      rf95.send((uint8_t*)msg, n);
      rf95.waitPacketSent();
    }

    seq = (seq + 1) & 0xFFFF;   // wrap at 65535 per ADR

    // Achieved sample rate over the last window — the measurement, printed with the build.
    if (sampleWindowStart == 0) sampleWindowStart = now;
    else if (now - sampleWindowStart >= 5000UL) {
      Serial.print("RATE: "); Serial.print(sampleCount * 1000.0f / (now - sampleWindowStart));
      Serial.print(" Hz achieved, baro failures "); Serial.print(baroFailures);
      // Reverts are transients the detector rejected. A non-zero count on the pad is the sled
      // telling you it was knocked -- and that it correctly declined to call it a launch.
      Serial.print(", launch reverts "); Serial.print(launchDet.reverts());
      Serial.print(", encode overflows "); Serial.println(encodeFailures);
      sampleCount = 0; sampleWindowStart = now;
    }
  }
}
