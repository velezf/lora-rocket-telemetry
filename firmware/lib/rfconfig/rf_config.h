#ifndef RF_CONFIG_H
#define RF_CONFIG_H

// BOTH-ENDS RF constants — the sled's copy of the link parameters.
//
// AUTHORITY: docs/adr/0005-telemetry-rate-and-rf-configuration.md (10 Hz at
// SF7 / BW500 / CR 4:5 / 17 dBm). A mismatch with the ground station
// (ground/rx/sx127x.py LoRaConfig) fails as SILENT total link loss — no error,
// simply no packets — so these values are guarded MECHANICALLY, not by prose:
// ground/rx/tests/test_rf_both_ends.py parses THIS FILE and compares it against
// the ground station's deployed defaults. Change either end alone and a test
// fails before the bench does.
//
// src/main.cpp additionally static_asserts these values against the RadioHead
// ModemConfigChoice it selects, so the enum name cannot drift from this header.
//
// Pure, portable C++ — no <Arduino.h>, no RadioHead (lib/ purity rule).

namespace rf {

constexpr unsigned long FREQ_HZ = 434000000;   // both ends; was RF95_FREQ in main.cpp
constexpr unsigned BANDWIDTH_KHZ = 500;        // both ends; the ADR's enabling change
constexpr unsigned SPREADING_FACTOR = 7;       // both ends
constexpr unsigned CODING_RATE_DENOM = 5;      // both ends; 4/5
// Sled-only. 23 -> 17 dBm as PART of the bandwidth decision, not separately:
// at 58.9 % duty the PA is keyed more than half the time, and 6 dB off is the
// answer to that thermal load (ADR 0005 §2 — "two changes, one justification").
constexpr int TX_POWER_DBM = 17;

}  // namespace rf

#endif  // RF_CONFIG_H
