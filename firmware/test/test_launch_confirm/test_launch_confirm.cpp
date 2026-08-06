#include <unity.h>
#include "launch.h"
#include "launch_confirm.h"

void setUp(void) {}
void tearDown(void) {}

// --- the defect, stated as a test so it cannot be argued about ---

void test_old_detector_latches_on_a_single_knock(void) {
    LaunchDetector d;
    TEST_ASSERT_TRUE(d.update(4.0f));       // ONE sample over threshold: in flight, forever
    TEST_ASSERT_TRUE(d.is_in_flight());
    d.update(1.0f); d.update(1.0f);         // back on the bench, motionless
    TEST_ASSERT_TRUE(d.is_in_flight());     // still "flying"
}

void test_confirm_rejects_the_same_knock(void) {
    // A 50 ms spike at 20 Hz is ONE sample. It must not launch.
    launch::Confirm c(3.0f, 100);
    unsigned long t = 0;
    TEST_ASSERT_FALSE(c.update(4.0f, t)); t += 50;   // spike begins
    TEST_ASSERT_FALSE(c.update(1.0f, t)); t += 50;   // and is over
    TEST_ASSERT_FALSE(c.update(1.0f, t));
    TEST_ASSERT_FALSE(c.is_in_flight());
}

void test_a_two_sample_knock_at_20hz_still_does_not_launch(void) {
    // 100 ms dwell means the SECOND sample must still be above at t=100.
    // A knock that decays within 100 ms is rejected.
    launch::Confirm c(3.0f, 100);
    unsigned long t = 0;
    TEST_ASSERT_FALSE(c.update(6.0f, t)); t += 50;
    TEST_ASSERT_FALSE(c.update(2.0f, t));            // decayed before the dwell elapsed
    TEST_ASSERT_FALSE(c.is_in_flight());
}

// --- a real launch is SUSTAINED: that is what makes dwell nearly free ---

void test_a_sustained_boost_launches_and_latches(void) {
    launch::Confirm c(3.0f, 100);
    unsigned long t = 0;
    int fires = 0;
    for (int i = 0; i < 40; i++) {           // 2 s of sustained boost at 20 Hz
        if (c.update(8.0f, t)) fires++;
        t += 50;
    }
    TEST_ASSERT_EQUAL_INT(1, fires);         // exactly once
    TEST_ASSERT_TRUE(c.is_in_flight());
}

void test_launch_fires_after_the_dwell_not_before(void) {
    launch::Confirm c(3.0f, 100);
    unsigned long t = 0;
    TEST_ASSERT_FALSE(c.update(8.0f, t));    // t=0:   above, dwell starts
    t += 50;
    TEST_ASSERT_FALSE(c.update(8.0f, t));    // t=50:  50 ms elapsed, not yet
    t += 50;
    TEST_ASSERT_TRUE(c.update(8.0f, t));     // t=100: dwell met
}

void test_a_dip_below_threshold_resets_the_dwell(void) {
    launch::Confirm c(3.0f, 100);
    unsigned long t = 0;
    c.update(8.0f, t);           t += 50;
    TEST_ASSERT_FALSE(c.update(1.0f, t)); t += 50;   // dropped out: not a launch
    TEST_ASSERT_FALSE(c.update(8.0f, t)); t += 50;   // starts over
    TEST_ASSERT_FALSE(c.update(8.0f, t));            // only 50 ms into the new dwell
    TEST_ASSERT_FALSE(c.is_in_flight());
}

// --- the constant is TIME, so a slow rate degrades to the legacy behaviour ---

void test_at_1hz_it_degrades_to_single_sample_behaviour(void) {
    // One sample per second is already >= the 100 ms dwell, so the SECOND above-threshold
    // sample fires. It cannot be worse than the old detector; it is one sample later.
    launch::Confirm c(3.0f, 100);
    unsigned long t = 0;
    TEST_ASSERT_FALSE(c.update(8.0f, t)); t += 1000;
    TEST_ASSERT_TRUE(c.update(8.0f, t));
}

void test_threshold_is_strictly_greater_than(void) {
    launch::Confirm c(3.0f, 0);              // dwell 0 == legacy immediate fire
    TEST_ASSERT_FALSE(c.update(3.0f, 0));    // exactly at threshold is NOT a launch
    TEST_ASSERT_TRUE(c.update(3.1f, 50));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_old_detector_latches_on_a_single_knock);
    RUN_TEST(test_confirm_rejects_the_same_knock);
    RUN_TEST(test_a_two_sample_knock_at_20hz_still_does_not_launch);
    RUN_TEST(test_a_sustained_boost_launches_and_latches);
    RUN_TEST(test_launch_fires_after_the_dwell_not_before);
    RUN_TEST(test_a_dip_below_threshold_resets_the_dwell);
    RUN_TEST(test_at_1hz_it_degrades_to_single_sample_behaviour);
    RUN_TEST(test_threshold_is_strictly_greater_than);
    return UNITY_END();
}
