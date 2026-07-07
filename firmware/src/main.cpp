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
#include <launch.h>
#include <apogee.h>
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

LaunchDetector launchDet;        // default 3.0 g threshold
apogee::Detector apogeeDet;

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

void loop() {
  if (!bmp.performReading()) { Serial.println("BMP read failed"); return; }
  float altitudeFt = pressure_to_altitude_ft(bmp.pressure / 100.0f, groundPressure);
  float tempC = bmp.temperature;

  sensors_event_t e;
  adxl.getEvent(&e);
  float g = accel_magnitude_g(e.acceleration.x, e.acceleration.y, e.acceleration.z);

  // Flight state from the pure detectors.
  if (launchDet.update(g)) launchTime = millis();
  bool inFlight = launchDet.is_in_flight();
  if (inFlight) {
    apogeeDet.update(altitudeFt);
    if (g > peakG) peakG = g;
  }
  bool descending = apogeeDet.is_descending();

  Packet p;
  p.sys    = SYS_ID;
  p.src    = SRC_ID;
  p.seq    = seq;
  p.state  = !inFlight ? 0u : (descending ? 2u : 1u);
  p.alt_ft = (int)lroundf(altitudeFt);
  p.max_ft = (int)lroundf(apogeeDet.max_altitude());   // 0 until first in-flight sample
  p.g      = g;
  p.pg     = peakG;
  p.temp_c = tempC;
  p.batt_v = readBatteryVoltage();
  p.met_s  = inFlight ? (unsigned int)((millis() - launchTime) / 1000UL) : 0u;

  char msg[128];
  size_t n = encode_packet(p, msg, sizeof(msg));

  Serial.print("TX: "); Serial.println(msg);
  rf95.send((uint8_t*)msg, n);
  rf95.waitPacketSent();

  seq = (seq + 1) & 0xFFFF;   // wrap at 65535 per ADR
  delay(1000);
}
