#ifndef RF_CONFIG_H
#define RF_CONFIG_H

// BOTH-ENDS RF constants — the sled's copy of the link parameters, AND the
// derivation of the SX127x modem registers from them.
//
// AUTHORITY: docs/adr/0005-telemetry-rate-and-rf-configuration.md (10 Hz at
// SF7 / BW500 / CR 4:5 / 17 dBm). A mismatch with the ground station
// (ground/rx/sx127x.py LoRaConfig) fails as SILENT total link loss — no error,
// simply no packets — so the weld is MECHANICAL at every link in the chain:
//   - main.cpp programs the radio with MODEM_REG_* derived HERE, at compile
//     time, from these constants — there is no enum whose meaning lives in a
//     comment (red-team finding 1: the old static_assert compared constants
//     to literals while the ModemConfigChoice could drift alone).
//   - The derivation formulas mirror ground/rx/sx127x.py modem_config1/2/3
//     and are pinned case-for-case against the ground's own register tests
//     by test/test_rfconfig (0x92/0x74/0x04 for the flight config).
//   - ground/rx/tests/test_rf_both_ends.py parses THIS FILE and compares both
//     the values and the resulting register semantics against the ground's
//     deployed defaults. Change either end alone and a test fails before the
//     bench goes silent.
//
// Pure, portable C++ — no <Arduino.h>, no RadioHead (lib/ purity rule).

namespace rf {

constexpr unsigned long FREQ_HZ = 434000000;   // both ends
constexpr unsigned BANDWIDTH_KHZ = 500;        // both ends; the ADR's enabling change
constexpr unsigned SPREADING_FACTOR = 7;       // both ends
constexpr unsigned CODING_RATE_DENOM = 5;      // both ends; 4/5
constexpr bool     CRC_ON = true;              // both ends
constexpr unsigned SYNC_WORD = 0x12;           // both ends; ground writes it, sled too
constexpr unsigned PREAMBLE_LEN = 8;           // both ends
// Sled-only. 23 -> 17 dBm as PART of the bandwidth decision, not separately:
// at 58.9 % duty the PA is keyed more than half the time, and 6 dB off is the
// answer to that thermal load (ADR 0005 §2 — "two changes, one justification").
constexpr int TX_POWER_DBM = 17;

// ---- register derivation (mirrors ground/rx/sx127x.py; pinned by test_rfconfig) ----

constexpr unsigned BW_INVALID = 0xFF;

// RegModemConfig1 bandwidth code. Only the bandwidths this project can actually
// fly are mapped; anything else is LOUDLY invalid rather than silently encoded.
constexpr unsigned bw_code(unsigned khz) {
    return khz == 125 ? 7 : khz == 250 ? 8 : khz == 500 ? 9 : BW_INVALID;
}

// RegModemConfig1: bw<<4 | (cr-4)<<1 | 0 (explicit header — ADR 0001's variable-
// length keyed format is why implicit-header SF6 was rejected).
constexpr unsigned char reg_modem_config1(unsigned bw_khz, unsigned cr_denom) {
    return static_cast<unsigned char>((bw_code(bw_khz) << 4) | ((cr_denom - 4) << 1));
}

// RegModemConfig2: sf<<4 | CRC-on bit.
constexpr unsigned char reg_modem_config2(unsigned sf, bool crc) {
    return static_cast<unsigned char>((sf << 4) | (crc ? 0x04 : 0x00));
}

// RegModemConfig3: AGC auto on; LDRO exactly when symbol time > 16 ms, i.e.
// 2^SF > 16 * BW_kHz — the same threshold ground's modem_config3 computes.
constexpr unsigned char reg_modem_config3(unsigned sf, unsigned bw_khz) {
    return static_cast<unsigned char>(
        0x04 | (((1UL << sf) > 16UL * bw_khz) ? 0x08 : 0x00));
}

// The bytes main.cpp programs. Compile-time: a bad constant above becomes a bad
// byte HERE, and test_rfconfig's flight-config pin fails.
constexpr unsigned char MODEM_REG_1D = reg_modem_config1(BANDWIDTH_KHZ, CODING_RATE_DENOM);
constexpr unsigned char MODEM_REG_1E = reg_modem_config2(SPREADING_FACTOR, CRC_ON);
constexpr unsigned char MODEM_REG_26 = reg_modem_config3(SPREADING_FACTOR, BANDWIDTH_KHZ);

static_assert(bw_code(BANDWIDTH_KHZ) != BW_INVALID,
              "BANDWIDTH_KHZ is not a bandwidth this project maps — extend bw_code() "
              "deliberately (both ends!) rather than letting it encode garbage");

}  // namespace rf

#endif  // RF_CONFIG_H
