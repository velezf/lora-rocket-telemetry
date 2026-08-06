#include <unity.h>
#include <cmath>
#include "imu.h"

void setUp(void) {}
void tearDown(void) {}

// ---------------- sensitivity tables (datasheet constants) ----------------

void test_gyro_sensitivity_matches_lsm6dsox_datasheet(void) {
    // LSM6DSOX datasheet Table 2 (mechanical characteristics), So_G, mdps/LSB.
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 4.375f, imu::gyro_mdps_per_lsb(125));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 8.75f, imu::gyro_mdps_per_lsb(250));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 17.50f, imu::gyro_mdps_per_lsb(500));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 35.0f, imu::gyro_mdps_per_lsb(1000));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 70.0f, imu::gyro_mdps_per_lsb(2000));
}

void test_gyro_sensitivity_rejects_unknown_range(void) {
    // An unsupported range must be REFUSED, not silently scaled. A wrong scale
    // is invisible in the data: it looks like a plausible roll rate.
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, imu::gyro_mdps_per_lsb(4000));
}

void test_mag_sensitivity_matches_lis3mdl_datasheet(void) {
    // LIS3MDL datasheet Table 3, LSB/gauss.
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 6842.0f, imu::mag_lsb_per_gauss(4));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 3421.0f, imu::mag_lsb_per_gauss(8));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 2281.0f, imu::mag_lsb_per_gauss(12));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1711.0f, imu::mag_lsb_per_gauss(16));
}

// ---------------- raw -> engineering units ----------------

void test_gyro_dps_scales_raw_count(void) {
    // 2000 dps range: 70 mdps/LSB. 1000 counts = 70000 mdps = 70 dps.
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 70.0f, imu::gyro_dps(1000, 70.0f));
}

void test_gyro_dps_is_signed(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, -70.0f, imu::gyro_dps(-1000, 70.0f));
}

void test_gyro_dps_full_scale_reaches_nominal_range(void) {
    // 32767 counts at 70 mdps/LSB ~= 2293 dps: full-scale count exceeds the
    // nominal 2000 dps range, which is why saturation must be tested on the
    // COUNT, not on the converted value.
    TEST_ASSERT_TRUE(imu::gyro_dps(32767, 70.0f) > 2000.0f);
}

void test_mag_ut_converts_gauss_to_microtesla(void) {
    // 6842 LSB/gauss; 6842 counts = 1 gauss = 100 uT.
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 100.0f, imu::mag_ut(6842, 6842.0f));
}

void test_mag_ut_is_signed(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, -100.0f, imu::mag_ut(-6842, 6842.0f));
}

// ---------------- saturation ----------------

void test_saturation_detects_both_rails(void) {
    TEST_ASSERT_TRUE(imu::is_saturated(32767));
    TEST_ASSERT_TRUE(imu::is_saturated(-32768));
}

void test_saturation_false_just_inside_the_rails(void) {
    TEST_ASSERT_FALSE(imu::is_saturated(32766));
    TEST_ASSERT_FALSE(imu::is_saturated(-32767));
    TEST_ASSERT_FALSE(imu::is_saturated(0));
}

// ---------------- derived flight quantities ----------------

void test_roll_rate_picks_the_longitudinal_axis(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 1.0f, imu::roll_rate_dps(1.0f, 2.0f, 3.0f, imu::Axis::X));
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 2.0f, imu::roll_rate_dps(1.0f, 2.0f, 3.0f, imu::Axis::Y));
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 3.0f, imu::roll_rate_dps(1.0f, 2.0f, 3.0f, imu::Axis::Z));
}

void test_tilt_is_zero_when_gravity_is_along_the_long_axis(void) {
    // Rocket vertical on the pad, long axis = Z, 1 g down the Z axis.
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.0f,
                             imu::tilt_off_axis_deg(0.0f, 0.0f, 9.80665f, imu::Axis::Z));
}

void test_tilt_is_ninety_when_gravity_is_perpendicular(void) {
    // Rocket lying on its side.
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 90.0f,
                             imu::tilt_off_axis_deg(9.80665f, 0.0f, 0.0f, imu::Axis::Z));
}

void test_tilt_is_forty_five_on_the_diagonal(void) {
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 45.0f,
                             imu::tilt_off_axis_deg(0.0f, 1.0f, 1.0f, imu::Axis::Z));
}

void test_tilt_folds_inversion_onto_the_same_angle(void) {
    // Nose-down 1 g is 180 deg of rotation but the same ANGLE OFF THE AXIS.
    // Folding to 0..90 is a decision, and it must be asserted, not assumed:
    // an unfolded 180 would read as "fully sideways" on the dashboard.
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.0f,
                             imu::tilt_off_axis_deg(0.0f, 0.0f, -9.80665f, imu::Axis::Z));
}

void test_tilt_rejects_a_zero_vector(void) {
    // Free fall or a dead read: there is no direction to report. Must be an
    // explicit sentinel, never 0 deg — 0 means "perfectly vertical", which is
    // the most dangerous possible thing to say when you know nothing.
    TEST_ASSERT_TRUE(imu::tilt_off_axis_deg(0.0f, 0.0f, 0.0f, imu::Axis::Z) < 0.0f);
}

// ---------------- gyro bias (the calibration primitive) ----------------

void test_bias_accumulator_starts_empty(void) {
    imu::BiasAccumulator b;
    TEST_ASSERT_EQUAL_INT(0, b.count());
    TEST_ASSERT_FALSE(b.ready(1));
}

void test_bias_accumulator_averages(void) {
    imu::BiasAccumulator b;
    b.add(1.0f, 10.0f, -4.0f);
    b.add(3.0f, 20.0f, -6.0f);
    TEST_ASSERT_EQUAL_INT(2, b.count());
    TEST_ASSERT_TRUE(b.ready(2));
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 2.0f, b.mean_x());
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 15.0f, b.mean_y());
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, -5.0f, b.mean_z());
}

void test_bias_accumulator_mean_of_nothing_is_zero_not_nan(void) {
    imu::BiasAccumulator b;
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, b.mean_x());
}

void test_bias_accumulator_rejects_motion(void) {
    // Calibration is only valid if the vehicle was STILL. A sample beyond the
    // gate must not be folded into the mean, or the bias silently absorbs
    // whatever the rocket was doing while somebody bumped the pad.
    imu::BiasAccumulator b;
    TEST_ASSERT_TRUE(b.add_if_still(0.5f, -0.5f, 0.2f, 1.0f));
    TEST_ASSERT_FALSE(b.add_if_still(0.5f, -0.5f, 40.0f, 1.0f));
    TEST_ASSERT_EQUAL_INT(1, b.count());
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_gyro_sensitivity_matches_lsm6dsox_datasheet);
    RUN_TEST(test_gyro_sensitivity_rejects_unknown_range);
    RUN_TEST(test_mag_sensitivity_matches_lis3mdl_datasheet);
    RUN_TEST(test_gyro_dps_scales_raw_count);
    RUN_TEST(test_gyro_dps_is_signed);
    RUN_TEST(test_gyro_dps_full_scale_reaches_nominal_range);
    RUN_TEST(test_mag_ut_converts_gauss_to_microtesla);
    RUN_TEST(test_mag_ut_is_signed);
    RUN_TEST(test_saturation_detects_both_rails);
    RUN_TEST(test_saturation_false_just_inside_the_rails);
    RUN_TEST(test_roll_rate_picks_the_longitudinal_axis);
    RUN_TEST(test_tilt_is_zero_when_gravity_is_along_the_long_axis);
    RUN_TEST(test_tilt_is_ninety_when_gravity_is_perpendicular);
    RUN_TEST(test_tilt_is_forty_five_on_the_diagonal);
    RUN_TEST(test_tilt_folds_inversion_onto_the_same_angle);
    RUN_TEST(test_tilt_rejects_a_zero_vector);
    RUN_TEST(test_bias_accumulator_starts_empty);
    RUN_TEST(test_bias_accumulator_averages);
    RUN_TEST(test_bias_accumulator_mean_of_nothing_is_zero_not_nan);
    RUN_TEST(test_bias_accumulator_rejects_motion);
    return UNITY_END();
}
