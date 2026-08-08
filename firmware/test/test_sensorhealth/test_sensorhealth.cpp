#include <unity.h>
#include "sensor_health.h"

void setUp(void) {}
void tearDown(void) {}

// Per-sensor read isolation (Phase 2 item 4): each sensor's failures are counted
// SEPARATELY, and health is judged in TIME (ms since last good read), not in counts —
// a count threshold means different things at 22 Hz and 1 Hz, which is the exact
// criterion-redefinition the repo's constants-in-time rule exists to prevent.

void test_failures_are_counted_per_sensor_independently(void) {
    sensors::Health h;
    h.note(sensors::BARO, false, 0);
    h.note(sensors::BARO, false, 59);
    h.note(sensors::IMU6, true,  59);
    TEST_ASSERT_EQUAL_UINT32(2, h.failures(sensors::BARO));
    TEST_ASSERT_EQUAL_UINT32(0, h.failures(sensors::IMU6));
    TEST_ASSERT_EQUAL_UINT32(0, h.failures(sensors::MAG));
}

void test_totals_are_monotonic_and_consecutive_resets_on_success(void) {
    sensors::Health h;
    h.note(sensors::MAG, false, 0);
    h.note(sensors::MAG, false, 59);
    TEST_ASSERT_EQUAL_UINT32(2, h.consecutive(sensors::MAG));
    h.note(sensors::MAG, true, 118);
    TEST_ASSERT_EQUAL_UINT32(0, h.consecutive(sensors::MAG));   // streak broken
    TEST_ASSERT_EQUAL_UINT32(2, h.failures(sensors::MAG));      // history kept
}

void test_health_is_time_since_last_good_read(void) {
    sensors::Health h;
    h.note(sensors::BARO, true, 1000);
    TEST_ASSERT_TRUE(h.healthy(sensors::BARO, 1400));           // 400 ms: fine
    TEST_ASSERT_FALSE(h.healthy(sensors::BARO, 1600));          // 600 ms > 500: stale
    h.note(sensors::BARO, true, 1700);
    TEST_ASSERT_TRUE(h.healthy(sensors::BARO, 1800));           // recovers instantly
}

void test_failed_reads_do_not_refresh_health(void) {
    // The stuck-baro lesson relocated: a sensor failing CONTINUOUSLY must go unhealthy
    // even though note() is being called constantly — only SUCCESS refreshes the clock.
    sensors::Health h;
    h.note(sensors::IMU6, true, 0);
    for (unsigned long t = 59; t <= 590; t += 59) h.note(sensors::IMU6, false, t);
    TEST_ASSERT_FALSE(h.healthy(sensors::IMU6, 590));
}

void test_a_sensor_never_seen_is_not_healthy(void) {
    // Power-on with a sensor absent: no successful read has EVER happened. Healthy
    // must be false, not "vacuously true because the clock never started" — that
    // would be a check that cannot fail.
    sensors::Health h;
    TEST_ASSERT_FALSE(h.healthy(sensors::MAG, 0));
    TEST_ASSERT_FALSE(h.healthy(sensors::MAG, 10000));
}

void test_the_staleness_bound_is_time_not_ticks(void) {
    sensors::Health slow, fast;
    slow.note(sensors::BARO, true, 0);
    slow.note(sensors::BARO, false, 1000);                       // 1 Hz attempt rate
    TEST_ASSERT_FALSE(slow.healthy(sensors::BARO, 1000));        // 1000 ms > 500
    fast.note(sensors::BARO, true, 0);
    for (unsigned long t = 59; t <= 472; t += 59)
        fast.note(sensors::BARO, false, t);                      // 17 Hz attempts
    TEST_ASSERT_TRUE(fast.healthy(sensors::BARO, 472));          // only 472 ms elapsed
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_failures_are_counted_per_sensor_independently);
    RUN_TEST(test_totals_are_monotonic_and_consecutive_resets_on_success);
    RUN_TEST(test_health_is_time_since_last_good_read);
    RUN_TEST(test_failed_reads_do_not_refresh_health);
    RUN_TEST(test_a_sensor_never_seen_is_not_healthy);
    RUN_TEST(test_the_staleness_bound_is_time_not_ticks);
    return UNITY_END();
}
