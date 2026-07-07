#include <unity.h>
#include <cmath>
#include "convert.h"

void setUp(void) {}
void tearDown(void) {}

void test_accel_magnitude_pure_z_is_one_g(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 1.0f, accel_magnitude_g(0.0f, 0.0f, 9.80665f));
}

void test_accel_magnitude_zero_is_zero(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, accel_magnitude_g(0.0f, 0.0f, 0.0f));
}

void test_accel_magnitude_3_4_0(void) {
    // sqrt(9+16)=5 m/s^2 -> 5/9.80665 g
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 5.0f / 9.80665f, accel_magnitude_g(3.0f, 4.0f, 0.0f));
}

void test_altitude_equal_pressure_is_zero(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.0f, pressure_to_altitude_ft(1013.25f, 1013.25f));
}

void test_altitude_lower_pressure_is_positive_matches_formula(void) {
    float pressure = 1000.0f;
    float ground = 1013.25f;
    float alt_m = 44330.0f * (1.0f - powf(pressure / ground, 1.0f / 5.255f));
    float expected_ft = alt_m * 3.28084f;
    float actual = pressure_to_altitude_ft(pressure, ground);
    TEST_ASSERT_TRUE(actual > 0.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-2f, expected_ft, actual);
}

void test_altitude_ground_higher_gives_positive_climb(void) {
    // ground pressure higher than measured pressure => climbed above ground
    TEST_ASSERT_TRUE(pressure_to_altitude_ft(950.0f, 1013.25f) > 0.0f);
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_accel_magnitude_pure_z_is_one_g);
    RUN_TEST(test_accel_magnitude_zero_is_zero);
    RUN_TEST(test_accel_magnitude_3_4_0);
    RUN_TEST(test_altitude_equal_pressure_is_zero);
    RUN_TEST(test_altitude_lower_pressure_is_positive_matches_formula);
    RUN_TEST(test_altitude_ground_higher_gives_positive_climb);
    return UNITY_END();
}
