#include <unity.h>
#include "apogee.h"
#include "apogee_confirm.h"
#include "profile.h"

void setUp(void) {}
void tearDown(void) {}

// Adapter so profile::run() can drive the timestamped Confirm from a sample index.
template <int HZ>
struct Timed {
    apogee::Confirm c;
    unsigned long   ms = 0;
    explicit Timed(float drop_ft, unsigned long dwell_ms) : c(drop_ft, dwell_ms) {}
    bool update(float alt) {
        bool fired = c.update(alt, ms);
        ms += 1000UL / HZ;
        return fired;
    }
};

// --- the defect being fixed: one noisy boost sample latches the OLD detector forever ---

void test_old_detector_latches_on_a_single_noisy_boost_sample(void) {
    apogee::Detector d;
    d.update(100.0f);
    d.update(400.0f);
    TEST_ASSERT_TRUE(d.update(399.0f));      // 1 ft of noise mid-boost -> apogee, latched
    TEST_ASSERT_TRUE(d.is_descending());
    d.update(2000.0f);                       // still climbing hard...
    TEST_ASSERT_TRUE(d.is_descending());     // ...but the record says DESCENDING for good
}

void test_confirm_ignores_the_same_noisy_sample(void) {
    apogee::Confirm c(20.0f, 300);
    unsigned long t = 0;
    TEST_ASSERT_FALSE(c.update(100.0f,  t));  t += 50;
    TEST_ASSERT_FALSE(c.update(400.0f,  t));  t += 50;
    TEST_ASSERT_FALSE(c.update(399.0f,  t));  t += 50;   // inside the 20 ft band
    TEST_ASSERT_FALSE(c.update(2000.0f, t));             // climb continues
    TEST_ASSERT_FALSE(c.is_descending());
}

// --- hysteresis: a drop must exceed the band ---

void test_a_drop_inside_the_band_never_fires(void) {
    apogee::Confirm c(20.0f, 300);
    unsigned long t = 0;
    c.update(1000.0f, t);
    for (int i = 0; i < 100; i++) { t += 50; TEST_ASSERT_FALSE(c.update(985.0f, t)); }
    TEST_ASSERT_FALSE(c.is_descending());
}

// --- dwell: a single deep spike is rejected, a sustained fall is not ---

void test_a_single_deep_spike_is_rejected(void) {
    apogee::Confirm c(20.0f, 300);
    unsigned long t = 0;
    c.update(1000.0f, t);            t += 50;
    c.update(900.0f,  t);            t += 50;   // one bad read, starts dwell
    TEST_ASSERT_FALSE(c.update(1000.0f, t));    // recovers -> dwell reset
    t += 50;
    TEST_ASSERT_FALSE(c.update(1001.0f, t));
    TEST_ASSERT_FALSE(c.is_descending());
}

void test_a_sustained_fall_fires_once_and_latches(void) {
    apogee::Confirm c(20.0f, 300);
    unsigned long t = 0;
    c.update(1000.0f, t);
    int fires = 0;
    for (int i = 0; i < 40; i++) { t += 50; if (c.update(900.0f, t)) fires++; }
    TEST_ASSERT_EQUAL_INT(1, fires);
    TEST_ASSERT_TRUE(c.is_descending());
}

void test_dwell_is_measured_in_TIME_not_samples(void) {
    // The same criterion at two rates must fire after the same ELAPSED time, not the same
    // sample count. This is the property that makes the constants survive whatever rate the
    // BMP390 actually delivers.
    // NOTE the dwell clock starts at the FIRST BELOW-BAND sample, not at the first update.
    // Both detectors below therefore fire at (first_below + 300 ms), whatever the rate.
    apogee::Confirm fast(20.0f, 300), slow(20.0f, 300);

    unsigned long t = 0;                       // 20 Hz: 50 ms steps
    fast.update(1000.0f, t);
    t += 50; fast.update(900.0f, t);           // first below at t=50 -> dwell starts
    while (t < 350) { t += 50; if (t < 350) TEST_ASSERT_FALSE(fast.update(900.0f, t)); }
    TEST_ASSERT_TRUE(fast.update(900.0f, t));  // t=350 == 50 + 300 ms
    TEST_ASSERT_EQUAL_UINT32(350, t);

    unsigned long s = 0;                       // 4 Hz: 250 ms steps
    slow.update(1000.0f, s);
    s += 250; TEST_ASSERT_FALSE(slow.update(900.0f, s));   // first below at s=250
    s += 250; TEST_ASSERT_FALSE(slow.update(900.0f, s));   // 250 ms elapsed: not yet
    s += 250; TEST_ASSERT_TRUE(slow.update(900.0f, s));    // 500 ms elapsed: fires
    // Same 300 ms criterion; the SLOWER rate just overshoots it by a fuller sample period.
    // That overshoot IS the cost of a low sample rate, and it is what 6.0a reduces.
}

// --- THE MEASUREMENT: rate is the variable, criterion is fixed ---

void test_20hz_beats_1hz_on_the_same_profile(void) {
    profile::Params p; profile::generate(p);

    Timed<1>  slow(20.0f, 300);
    Timed<20> fast(20.0f, 300);
    profile::Result r1 = profile::run(slow, p, 1.0f);
    profile::Result r20 = profile::run(fast, p, 20.0f);

    TEST_ASSERT_TRUE(r1.fired);
    TEST_ASSERT_TRUE(r20.fired);
    // Both must be LATE (detection cannot precede the event) ...
    TEST_ASSERT_TRUE(r1.latency_s  >= 0.0f);
    TEST_ASSERT_TRUE(r20.latency_s >= 0.0f);
    // ... and 20 Hz must lose materially less altitude than 1 Hz.
    TEST_ASSERT_TRUE(r20.fell_ft < r1.fell_ft);
    TEST_ASSERT_TRUE(r20.latency_s < r1.latency_s);
}

void test_the_profile_has_sane_analytic_ground_truth(void) {
    profile::Params p; profile::generate(p);
    TEST_ASSERT_TRUE(p.apogee_ft > 500.0f);        // a plausible L1 altitude
    TEST_ASSERT_TRUE(p.apogee_s  > p.burn_s);      // apogee is after burnout
    // altitude at apogee is the maximum: sample either side and confirm
    TEST_ASSERT_TRUE(profile::altitude_ft(p, p.apogee_s - 0.5f) < p.apogee_ft);
    TEST_ASSERT_TRUE(profile::altitude_ft(p, p.apogee_s + 0.5f) < p.apogee_ft);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_old_detector_latches_on_a_single_noisy_boost_sample);
    RUN_TEST(test_confirm_ignores_the_same_noisy_sample);
    RUN_TEST(test_a_drop_inside_the_band_never_fires);
    RUN_TEST(test_a_single_deep_spike_is_rejected);
    RUN_TEST(test_a_sustained_fall_fires_once_and_latches);
    RUN_TEST(test_dwell_is_measured_in_TIME_not_samples);
    RUN_TEST(test_20hz_beats_1hz_on_the_same_profile);
    RUN_TEST(test_the_profile_has_sane_analytic_ground_truth);
    return UNITY_END();
}
