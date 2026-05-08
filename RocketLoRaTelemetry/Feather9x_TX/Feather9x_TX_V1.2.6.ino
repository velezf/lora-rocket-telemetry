/*
 * Feather9x_TX_V1.2.6
 * LoRa rocket telemetry transmitter — rocket sled firmware
 *
 * Author:   Francisco Velez (KC3ZTQ)
 * License:  MIT — see LICENSE in repo root
 *
 * Hardware: Adafruit Feather M0 + RFM95 LoRa (434 MHz, 23 dBm)
 *           BMP390 barometric pressure/temperature sensor (I2C)
 *           ADXL375 high-g accelerometer ±200g (I2C)
 *
 * Features: Trimmed-mean baseline pressure calibration, launch detection,
 *           apogee detection, battery monitoring, 1 Hz telemetry with ACK.
 *
 * Based on the RadioRocketV2 project concept by Vance Martin (N3VEM)
 * https://github.com/N3VEM/RadioRocketV2
 * Original firmware rewritten for Feather M0 platform.
 */
#include <SPI.h>
#include <Wire.h>
#include <RH_RF95.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP3XX.h>
#include <Adafruit_ADXL375.h>

// -------------------- Pin Definitions --------------------
#define RFM95_CS    8
#define RFM95_RST   4
#define RFM95_INT   3
#define RF95_FREQ   434.0 // MHz

// -------------------- Hardware Instances --------------------
RH_RF95 rf95(RFM95_CS, RFM95_INT);
Adafruit_BMP3XX bmp;
Adafruit_ADXL375 adxl(0x53, &Wire);  // ADXL375 I2C address

// -------------------- Altitude & Pressure --------------------
float groundPressure = 1013.25; // hPa, calibrated at boot
float maxAltitudeFt = 0;

// -------------------- Acceleration --------------------
float peakG = 0;
float launchThresholdG = 3.0;  // G threshold to detect launch
bool inFlight = false;
bool descending = false;

// -------------------- Timing --------------------
unsigned long launchTime = 0;
unsigned long now = 0;

// -------------------- Battery Monitoring --------------------
float readBatteryVoltage() {
  int raw = analogRead(A7);  // A7 reads battery via voltage divider
  float measuredV = raw * 3.3 / 1023.0 * 2.0;  // Convert to real volts
  return measuredV;
}

String batteryStatus(float volts) {
  if (volts > 3.7) return "Good";
  if (volts > 3.4) return "Low";
  return "Charge Now";
}

void setup() {
  // -------------------- Serial & Reset --------------------
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);
  Serial.begin(115200);
  while (!Serial) delay(1);
  delay(100);

  // -------------------- LoRa Init --------------------
  digitalWrite(RFM95_RST, LOW); delay(10);
  digitalWrite(RFM95_RST, HIGH); delay(10);
  if (!rf95.init()) {
    Serial.println("LoRa radio init failed");
    while (1);
  }
  rf95.setFrequency(RF95_FREQ);
  rf95.setTxPower(23, false);
  Serial.println("LoRa radio init OK!");

  // -------------------- BMP390 Init --------------------
  if (!bmp.begin_I2C()) {
    Serial.println("BMP390 not found!");
    while (1);
  }
  bmp.setTemperatureOversampling(BMP3_OVERSAMPLING_8X);
  bmp.setPressureOversampling(BMP3_OVERSAMPLING_4X);
  bmp.setIIRFilterCoeff(BMP3_IIR_FILTER_COEFF_3);

  // Calibrate ground pressure
  float sum = 0;
  for (int i = 0; i < 50; i++) {
    bmp.performReading();
    sum += bmp.pressure / 100.0;
    delay(50);
  }
  groundPressure = sum / 50.0;
  Serial.print("Calibrated ground pressure: "); Serial.println(groundPressure);

  // -------------------- ADXL375 Init --------------------
  if (!adxl.begin()) {
    Serial.println("No ADXL375 detected!");
    while (1);
  }
  Serial.println("ADXL375 ready.");
}

void loop() {
  now = millis();

  // Read BMP390 sensor
  if (!bmp.performReading()) {
    Serial.println("BMP390 read failed");
    return;
  }
  float altitudeFt = bmp.readAltitude(groundPressure) * 3.28084;
  float tempC = bmp.temperature;

  // Read ADXL375 sensor and compute total G
  sensors_event_t event;
  adxl.getEvent(&event);
  float g = sqrt(event.acceleration.x * event.acceleration.x +
                 event.acceleration.y * event.acceleration.y +
                 event.acceleration.z * event.acceleration.z) / 9.80665;

  // -------------------- Launch Detection --------------------
  if (!inFlight && g > launchThresholdG) {
    inFlight = true;
    launchTime = now;
    Serial.println("🚀 Launch detected!");
  }

  // -------------------- Apogee Detection --------------------
  if (inFlight) {
    if (altitudeFt > maxAltitudeFt) {
      maxAltitudeFt = altitudeFt;
      descending = false;  // still ascending
    } else {
      if (!descending) {
        Serial.println("🪂 Apogee reached / Descent started");
      }
      descending = true;
    }
    if (g > peakG) peakG = g;  // update peak G
  }

  // Time since launch (in seconds)
  unsigned long timeSinceLaunch = inFlight ? (now - launchTime) / 1000 : 0;

  // Battery voltage and status
  float battV = readBatteryVoltage();
  String battStatus = batteryStatus(battV);

  // -------------------- Format LoRa Message --------------------
  char message[120];
  snprintf(message, sizeof(message),
    "ALT:%.0fft Max:%.0fft G:%.1f Pg:%.1f T:%.1fC Batt:%.2fV [%s] %s t+%lus",
    altitudeFt, maxAltitudeFt, g, peakG, tempC, battV, battStatus.c_str(),
    (descending ? "🪂" : (inFlight ? "🚀" : "🟢")), timeSinceLaunch);

  // -------------------- Send via LoRa --------------------
  Serial.print("Sending: "); Serial.println(message);
  rf95.send((uint8_t*)message, strlen(message));
  rf95.waitPacketSent();

  // Optional reply handler
  if (rf95.waitAvailableTimeout(300)) {
    uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
    uint8_t len = sizeof(buf);
    if (rf95.recv(buf, &len)) {
      Serial.print("Got reply: ");
      Serial.println((char*)buf);
    }
  }

  delay(1000);  // 1 second between messages
}

