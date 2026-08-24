#include <unity.h>
#include <cmath>
#include "velocity.h"
#include "profile.h"

void setUp(void) {}
void tearDown(void) {}

// Analytic vertical velocity for a profile — the INDEPENDENT ground truth (evidence-trust
// pattern #4: a test derived from the same model as the implementation measures
// self-consistency, not correctness). This derivative is written from the physics in
// profile.h, not from the estimator: v = a*t while burning, v_bo − g·dt while coasting.
static float true_velocity_fps(const profile::Params& p, float t) {
    const float g = 32.174f;
    const float a = p.boost_accel_g * g;
    if (t <= 0.0f) return 0.0f;
    if (t < p.burn_s) return a * t;
    return a * p.burn_s - g * (t - p.burn_s);
}

// --- basic contract ---

void test_no_estimate_before_two_samples(void) {
    velocity::Estimator v;
    TEST_ASSERT_FALSE(v.has());
    TEST_ASSERT_EQUAL_FLOAT(0.0f, v.vel_fps());
    v.update(100.0f, 1000);
    TEST_ASSERT_FALSE(v.has());              // one point has no slope
    TEST_ASSERT_EQUAL_FLOAT(0.0f, v.vel_fps());
    v.update(105.0f, 1050);
    TEST_ASSERT_TRUE(v.has());
}

void test_zero_dt_sample_is_ignored_not_a_division(void) {
    velocity::Estimator v;
    v.update(100.0f, 1000);
    v.update(105.0f, 1050);
    const float before = v.vel_fps();
    v.update(999.0f, 1050);                  // same timestamp: no interval to divide by
    TEST_ASSERT_EQUAL_FLOAT(before, v.vel_fps());
}

// --- convergence on a constant rate ---

void test_converges_on_a_constant_climb_rate(void) {
    velocity::Estimator v;                   // default tau
    unsigned long t = 0;
    float alt = 0.0f;
    for (int i = 0; i < 60; i++) {           // 3 s at 20 Hz, 100 ft/s
        v.update(alt, t);
        alt += 5.0f; t += 50;
    }
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 100.0f, v.vel_fps());
}

void test_descent_is_negative(void) {
    velocity::Estimator v;
    unsigned long t = 0;
    float alt = 1000.0f;
    for (int i = 0; i < 60; i++) {
        v.update(alt, t);
        alt -= 1.5f; t += 50;                // −30 ft/s, chute-like
    }
    TEST_ASSERT_FLOAT_WITHIN(1.0f, -30.0f, v.vel_fps());
}

// --- SMOOTHING IS A TIME CONSTANT, NOT A SAMPLE COUNT (same discipline as
// apogee::Confirm: the achieved sample rate is measured, not chosen, so the filter
// must mean the same thing at whatever rate the BMP390 delivers). The same tau at two
// rates must converge to the same value on the same signal.

void test_smoothing_is_rate_independent(void) {
    velocity::Estimator v10, v40;
    for (int i = 0; i <= 30 * 10; i++)       // 3 s at 10 Hz
        v10.update(100.0f * (i / 10.0f), (unsigned long)(i * 100));
    for (int i = 0; i <= 30 * 40; i++)       // 3 s at 40 Hz
        v40.update(100.0f * (i / 40.0f), (unsigned long)(i * 25));
    TEST_ASSERT_FLOAT_WITHIN(2.0f, v10.vel_fps(), v40.vel_fps());
}

// --- a sample gap (failed baro reads) widens dt; the estimate stays sane ---

void test_survives_a_sample_gap(void) {
    velocity::Estimator v;
    unsigned long t = 0;
    float alt = 0.0f;
    for (int i = 0; i < 40; i++) { v.update(alt, t); alt += 5.0f; t += 50; }
    t += 450;  alt += 45.0f;                 // 10 ticks lost to a wedged read
    v.update(alt, t);                        // rate was 100 ft/s throughout
    TEST_ASSERT_FLOAT_WITHIN(5.0f, 100.0f, v.vel_fps());
}

// --- against the profile's analytic truth ---

void test_tracks_coast_phase_within_tolerance(void) {
    profile::Params p;                       // 1.6 s burn at 12 g -> F-class-ish
    profile::generate(p);
    velocity::Estimator v;
    const float hz = 20.0f, dt = 1.0f / hz;
    float worst = 0.0f;
    for (float t = 0.0f; t < p.apogee_s; t += dt) {
        v.update(profile::altitude_ft(p, t), (unsigned long)(t * 1000.0f));
        // judge only the coast phase, clear of the boost transient (EMA lag during a
        // 12 g ramp is ~a·tau and is bounded by the peak-capture test below instead)
        if (t > p.burn_s + 0.5f) {
            const float err = std::fabs(v.vel_fps() - true_velocity_fps(p, t));
            if (err > worst) worst = err;
        }
    }
    // coast decelerates at 1 g, so EMA lag costs ~g·tau ≈ 6.4 ft/s at tau=200 ms
    TEST_ASSERT_TRUE_MESSAGE(worst < 12.0f, "coast-phase velocity error exceeded 12 ft/s");
}

void test_captures_burnout_peak_within_15_percent(void) {
    profile::Params p;
    profile::generate(p);
    const float v_bo = p.boost_accel_g * 32.174f * p.burn_s;   // analytic burnout velocity
    velocity::Estimator v;
    const float hz = 20.0f, dt = 1.0f / hz;
    float peak = 0.0f;
    for (float t = 0.0f; t < p.apogee_s; t += dt) {
        v.update(profile::altitude_ft(p, t), (unsigned long)(t * 1000.0f));
        if (v.vel_fps() > peak) peak = v.vel_fps();
    }
    TEST_ASSERT_TRUE_MESSAGE(peak > 0.85f * v_bo, "smoothing ate the burnout peak");
    TEST_ASSERT_TRUE_MESSAGE(peak < 1.05f * v_bo, "peak exceeds physics");
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_no_estimate_before_two_samples);
    RUN_TEST(test_zero_dt_sample_is_ignored_not_a_division);
    RUN_TEST(test_converges_on_a_constant_climb_rate);
    RUN_TEST(test_descent_is_negative);
    RUN_TEST(test_smoothing_is_rate_independent);
    RUN_TEST(test_survives_a_sample_gap);
    RUN_TEST(test_tracks_coast_phase_within_tolerance);
    RUN_TEST(test_captures_burnout_peak_within_15_percent);
    return UNITY_END();
}
