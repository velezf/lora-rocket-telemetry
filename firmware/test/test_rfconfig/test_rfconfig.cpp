#include <unity.h>
#include "rf_config.h"

void setUp(void) {}
void tearDown(void) {}

// The sled's modem registers are DERIVED from rf_config.h — the same derivation the
// ground station performs in ground/rx/sx127x.py (modem_config1/2/3). These tests pin
// the derivation on the sled side exactly as test_sx127x.py pins it on the ground side,
// so the two ends' register semantics are mirrored case-for-case across the languages.

// --- the flight config: must equal the bytes the ground pins for its own default
// (test_sx127x.py test_configure_modem_registers_for_bw500_sf7_cr45_crc: 0x92/0x74/0x04)
// and the bytes RadioHead's Bw500Cr45Sf128 table row carries (RH_RF95.cpp) ---

void test_flight_config_registers(void) {
    TEST_ASSERT_EQUAL_HEX8(0x92, rf::MODEM_REG_1D);   // BW500, CR4/5, explicit header
    TEST_ASSERT_EQUAL_HEX8(0x74, rf::MODEM_REG_1E);   // SF7, CRC on
    TEST_ASSERT_EQUAL_HEX8(0x04, rf::MODEM_REG_26);   // AGC on, LDRO off (0.256 ms symbol)
}

// --- formula cases mirroring ground's TestConfigEncoding.test_sf9_bw250_cr48_registers ---

void test_derivation_matches_grounds_sf9_bw250_cr48_case(void) {
    TEST_ASSERT_EQUAL_HEX8(0x88, rf::reg_modem_config1(250, 8));  // (8<<4)|(4<<1)
    TEST_ASSERT_EQUAL_HEX8(0x94, rf::reg_modem_config2(9, true)); // (9<<4)|0x04
}

void test_crc_off_clears_the_crc_bit(void) {
    TEST_ASSERT_EQUAL_HEX8(0x70, rf::reg_modem_config2(7, false));
}

// --- LDRO: set exactly when symbol time exceeds 16 ms (2^SF > 16 * BW_kHz),
// the same threshold ground's modem_config3 computes ---

void test_ldro_engages_for_long_symbols(void) {
    TEST_ASSERT_EQUAL_HEX8(0x0C, rf::reg_modem_config3(12, 125)); // 32.8 ms symbol: AGC|LDRO
    TEST_ASSERT_EQUAL_HEX8(0x04, rf::reg_modem_config3(7, 500));  // 0.256 ms: AGC only
    TEST_ASSERT_EQUAL_HEX8(0x04, rf::reg_modem_config3(9, 500));  // 1.02 ms: AGC only
}

// --- the bandwidth table can MISS (anti-hollow): an unknown bandwidth is loud,
// not silently encoded as something else ---

void test_unknown_bandwidth_is_invalid_not_silent(void) {
    TEST_ASSERT_EQUAL_UINT(rf::BW_INVALID, rf::bw_code(999));
    TEST_ASSERT_EQUAL_UINT(7, rf::bw_code(125));
    TEST_ASSERT_EQUAL_UINT(8, rf::bw_code(250));
    TEST_ASSERT_EQUAL_UINT(9, rf::bw_code(500));
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_flight_config_registers);
    RUN_TEST(test_derivation_matches_grounds_sf9_bw250_cr48_case);
    RUN_TEST(test_crc_off_clears_the_crc_bit);
    RUN_TEST(test_ldro_engages_for_long_symbols);
    RUN_TEST(test_unknown_bandwidth_is_invalid_not_silent);
    return UNITY_END();
}
