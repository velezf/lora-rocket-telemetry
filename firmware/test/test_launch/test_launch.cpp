#include <unity.h>
#include "launch.h"

void setUp(void) {}
void tearDown(void) {}

// Below the threshold: no launch, not in flight.
void test_below_threshold_stays_grounded(void) {
    LaunchDetector d;  // default threshold 3.0 g
    TEST_ASSERT_FALSE(d.update(0.0f));
    TEST_ASSERT_FALSE(d.update(1.0f));
    TEST_ASSERT_FALSE(d.update(2.9f));
    TEST_ASSERT_FALSE(d.is_in_flight());
}

// Crossing the threshold: update() fires exactly once, then in flight latches.
void test_crossing_threshold_fires_once(void) {
    LaunchDetector d;
    TEST_ASSERT_FALSE(d.update(1.0f));
    TEST_ASSERT_TRUE(d.update(4.0f));   // launch detected at this moment
    TEST_ASSERT_TRUE(d.is_in_flight());
    TEST_ASSERT_FALSE(d.update(5.0f));  // already in flight, does not re-fire
}

// Once in flight, dropping below threshold keeps us in flight; no re-fire.
void test_stays_in_flight_after_g_drops(void) {
    LaunchDetector d;
    TEST_ASSERT_TRUE(d.update(3.5f));
    TEST_ASSERT_TRUE(d.is_in_flight());
    TEST_ASSERT_FALSE(d.update(0.0f));
    TEST_ASSERT_FALSE(d.update(-2.0f));
    TEST_ASSERT_TRUE(d.is_in_flight());
    TEST_ASSERT_FALSE(d.update(9.0f));  // spikes again, still no re-fire
    TEST_ASSERT_TRUE(d.is_in_flight());
}

// Exactly at the threshold is NOT a launch (strict greater-than, matches V1).
void test_exactly_at_threshold_is_not_launch(void) {
    LaunchDetector d;
    TEST_ASSERT_FALSE(d.update(3.0f));
    TEST_ASSERT_FALSE(d.is_in_flight());
}

// Constructor-configurable threshold.
void test_custom_threshold(void) {
    LaunchDetector d(10.0f);
    TEST_ASSERT_FALSE(d.update(4.0f));
    TEST_ASSERT_FALSE(d.is_in_flight());
    TEST_ASSERT_TRUE(d.update(10.5f));
    TEST_ASSERT_TRUE(d.is_in_flight());
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_below_threshold_stays_grounded);
    RUN_TEST(test_crossing_threshold_fires_once);
    RUN_TEST(test_stays_in_flight_after_g_drops);
    RUN_TEST(test_exactly_at_threshold_is_not_launch);
    RUN_TEST(test_custom_threshold);
    return UNITY_END();
}
