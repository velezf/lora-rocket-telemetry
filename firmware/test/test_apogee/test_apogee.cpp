#include <unity.h>
#include "apogee.h"

void setUp(void) {}
void tearDown(void) {}

// Monotonically rising altitudes: never apogee, max tracks the peak.
void test_rising_never_apogees(void) {
    apogee::Detector d;
    float samples[] = {0.0f, 10.0f, 25.0f, 40.0f, 100.0f};
    for (float a : samples) {
        TEST_ASSERT_FALSE(d.update(a));
        TEST_ASSERT_FALSE(d.is_descending());
    }
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, d.max_altitude());
}

// A drop after rising fires apogee exactly once and latches descending.
void test_drop_fires_apogee_once(void) {
    apogee::Detector d;
    TEST_ASSERT_FALSE(d.update(10.0f));
    TEST_ASSERT_FALSE(d.update(50.0f));
    TEST_ASSERT_FALSE(d.update(120.0f));   // peak
    TEST_ASSERT_TRUE(d.update(119.0f));    // first drop -> apogee
    TEST_ASSERT_TRUE(d.is_descending());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 120.0f, d.max_altitude());
}

// Further drops stay descending; apogee never fires again.
void test_further_drops_do_not_refire(void) {
    apogee::Detector d;
    d.update(30.0f);
    d.update(90.0f);              // peak
    TEST_ASSERT_TRUE(d.update(80.0f));   // apogee fires
    TEST_ASSERT_FALSE(d.update(70.0f));  // still descending, no refire
    TEST_ASSERT_FALSE(d.update(10.0f));
    TEST_ASSERT_TRUE(d.is_descending());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 90.0f, d.max_altitude());
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_rising_never_apogees);
    RUN_TEST(test_drop_fires_apogee_once);
    RUN_TEST(test_further_drops_do_not_refire);
    return UNITY_END();
}
