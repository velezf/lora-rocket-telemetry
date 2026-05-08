/*
 * Feather9x_RX_v1.1
 * LoRa rocket telemetry receiver — ground station firmware
 *
 * Author:   Francisco Velez (KC3ZTQ)
 * License:  MIT — see LICENSE in repo root
 *
 * Hardware: Adafruit Feather M0 + RFM95 LoRa (434 MHz)
 *
 * Features: Packet receive, field parsing, pretty-print to USB serial,
 *           RSSI reporting, ACK reply to TX.
 *
 * Based on the RadioRocketV2 project concept by Vance Martin (N3VEM)
 * https://github.com/N3VEM/RadioRocketV2
 * Original firmware rewritten for Feather M0 platform.
 */
// Feather9x_RX
// -*- mode: C++ -*-
// Example sketch showing how to create a simple messaging client (receiver)
// with the RH_RF95 class. RH_RF95 class does not provide for addressing or
// reliability, so you should only use RH_RF95 if you do not need the higher
// level messaging abilities.
// It is designed to work with the other example Feather9x_TX
// This is running on the feather mounted in the box
// Parses and displays: Temperature, Pressure, Battery Voltage + Status, Altitude (current), Apogee (from TX)
// Still tracks its own RX-side apogee (optional but useful), Includes alerts for descent detection
#include <SPI.h>
#include <RH_RF95.h>

// -------------------- Pin Definitions --------------------
#define RFM95_CS    8
#define RFM95_RST   4
#define RFM95_INT   3
#define RF95_FREQ   434.0

// -------------------- LoRa Driver --------------------
RH_RF95 rf95(RFM95_CS, RFM95_INT);

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);

  Serial.begin(115200);
  while (!Serial) delay(1);
  delay(100);

  Serial.println("LoRa RX Ready");

  // Reset radio
  digitalWrite(RFM95_RST, LOW); delay(10);
  digitalWrite(RFM95_RST, HIGH); delay(10);

  if (!rf95.init()) {
    Serial.println("LoRa radio init failed");
    while (1);
  }

  rf95.setFrequency(RF95_FREQ);
  rf95.setTxPower(23, false);
  Serial.println("LoRa radio initialized");
}

void loop() {
  if (rf95.available()) {
    uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
    uint8_t len = sizeof(buf);

    if (rf95.recv(buf, &len)) {
      digitalWrite(LED_BUILTIN, HIGH);

      // Print raw message
      Serial.print("Received: ");
      Serial.println((char*)buf);
      Serial.print("RSSI: ");
      Serial.println(rf95.lastRssi());

      // Parse message using sscanf
      float alt, maxAlt, g, peakG, temp, battV;
      char battStatus[20], flightState[10];
      unsigned long timeSec;

      int parsed = sscanf((char*)buf,
        "ALT:%fft Max:%fft G:%f Pg:%f T:%fC Batt:%fV [%[^]]] %s t+%lus",
        &alt, &maxAlt, &g, &peakG, &temp, &battV, battStatus, flightState, &timeSec);

      if (parsed >= 9) {
        Serial.println("---------- Parsed Telemetry ----------");
        Serial.print("Altitude: ");      Serial.print(alt);      Serial.println(" ft");
        Serial.print("Max Altitude: ");  Serial.print(maxAlt);   Serial.println(" ft");
        Serial.print("Current G: ");     Serial.println(g, 2);
        Serial.print("Peak G: ");        Serial.println(peakG, 2);
        Serial.print("Temp: ");          Serial.print(temp);     Serial.println(" °C");
        Serial.print("Battery: ");       Serial.print(battV);    Serial.print(" V (");
        Serial.print(battStatus);        Serial.println(")");
        Serial.print("Flight: ");        Serial.println(flightState);
        Serial.print("Time Since Launch: "); Serial.print(timeSec); Serial.println(" s");
        Serial.println("--------------------------------------");
      } else {
        Serial.println("⚠️ Failed to parse telemetry data.");
      }

      digitalWrite(LED_BUILTIN, LOW);
    } else {
      Serial.println("Receive failed");
    }
  }
}

