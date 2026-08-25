#include <unity.h>
#include "ninedof.h"

void setUp(void) {}
void tearDown(void) {}

// Raw->unit conversions for the 9-DoF raw-read path (feat/i2c-hardening). These
// replace the vendored getEvent() paths — which discard I2C status — so the scale
// factors the vendored drivers applied must be reproduced EXACTLY, or the wire
// values silently change meaning across the swap. Pinned against A1.4's own
// derivation: gyro int16 x 70 mdps/LSB at +/-2000 dps FS; mag 6842 LSB/gauss at
// +/-4 gauss, 1 gauss = 100 uT.

void test_gyro_scale_matches_a14_derivation(void) {
    // A1.4's +/-2293.8 dps figure IS the negative int16 extreme: -32768 x 0.07.
    TEST_ASSERT_FLOAT_WITHIN(0.01f, -2293.76f, ninedof::gyro_raw_to_dps(-32768));
    TEST_ASSERT_FLOAT_WITHIN(0.01f,  2293.69f, ninedof::gyro_raw_to_dps(32767));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.07f,    ninedof::gyro_raw_to_dps(1));
    TEST_ASSERT_EQUAL_FLOAT(0.0f,              ninedof::gyro_raw_to_dps(0));
}

void test_mag_scale_matches_a14_derivation(void) {
    // A1.4's +/-478.9 uT figure: 32768 / 6842 LSB-per-gauss x 100 uT-per-gauss.
    TEST_ASSERT_FLOAT_WITHIN(0.05f, -478.92f, ninedof::mag_raw_to_ut(-32768));
    TEST_ASSERT_FLOAT_WITHIN(0.05f,  478.90f, ninedof::mag_raw_to_ut(32767));
    TEST_ASSERT_EQUAL_FLOAT(0.0f,             ninedof::mag_raw_to_ut(0));
    // A realistic Earth-field reading survives the round trip: ~40 uT -> raw ~2737.
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 40.0f, ninedof::mag_raw_to_ut(2737));
}

// Little-endian frame parsing (both chips emit X_L X_H Y_L Y_H Z_L Z_H): the
// negative-value path is the one a byte-order mistake corrupts silently.
void test_le16_parses_sign_correctly(void) {
    const unsigned char neg[] = {0x00, 0x80};   // -32768
    const unsigned char one[] = {0x01, 0x00};   // 1
    const unsigned char m1[]  = {0xFF, 0xFF};   // -1
    TEST_ASSERT_EQUAL_INT16(-32768, ninedof::le16(neg));
    TEST_ASSERT_EQUAL_INT16(1,      ninedof::le16(one));
    TEST_ASSERT_EQUAL_INT16(-1,     ninedof::le16(m1));
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_gyro_scale_matches_a14_derivation);
    RUN_TEST(test_mag_scale_matches_a14_derivation);
    RUN_TEST(test_le16_parses_sign_correctly);
    return UNITY_END();
}
