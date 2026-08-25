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

// --- NOISE (red-team finding 5): noise rejection is the property Vel EXISTS for —
// ADR 0005 §4's whole justification is "differentiated on the ground it would be
// noise; onboard it is the real curve". Every test above drives noise-free signals,
// which asserts tracking but never that claim. This one injects deterministic
// baro-like jitter and bounds the output's usability directly. ---

// Deterministic LCG so the "noise" is identical on every run and every platform —
// a seeded reproducible sequence, not randomness.
static float lcg_noise_ft(unsigned long& state, float amplitude_ft) {
    state = state * 1664525UL + 1013904223UL;
    const float u = ((state >> 16) & 0x7FFF) / 32767.0f;   // [0,1]
    return (u - 0.5f) * 2.0f * amplitude_ft;               // [-amp, +amp]
}

void test_noise_rejection_is_real_not_assumed(void) {
    profile::Params p;
    profile::generate(p);
    const float hz = 20.0f, dt = 1.0f / hz;
    const float noise_amp_ft = 2.0f;    // BMP390 at 4x/IIR-3: ~1-2 ft sample jitter

    velocity::Estimator v;
    unsigned long seed = 0xC0FFEEUL;
    float worst_smoothed = 0.0f, sum_sq = 0.0f;
    int   n = 0;
    float prev_noisy_alt = 0.0f;
    float worst_raw = 0.0f;
    bool  have_prev = false;

    for (float t = 0.0f; t < p.apogee_s; t += dt) {
        const float noisy_alt = profile::altitude_ft(p, t) + lcg_noise_ft(seed, noise_amp_ft);
        v.update(noisy_alt, (unsigned long)(t * 1000.0f));

        if (have_prev && t > p.burn_s + 0.5f) {             // judge the coast phase
            const float truth = true_velocity_fps(p, t);
            const float raw   = (noisy_alt - prev_noisy_alt) / dt;   // ground-side dh/dt
            const float e_s   = std::fabs(v.vel_fps() - truth);
            const float e_r   = std::fabs(raw - truth);
            if (e_s > worst_smoothed) worst_smoothed = e_s;
            if (e_r > worst_raw)      worst_raw = e_r;
            sum_sq += e_s * e_s; n++;
        }
        prev_noisy_alt = noisy_alt;
        have_prev = true;
    }
    const float rms = std::sqrt(sum_sq / n);

    // ANTI-HOLLOW: the injected noise must actually hurt the raw derivative — if the
    // injection silently broke (zeros), raw error would be small and this fails.
    TEST_ASSERT_TRUE_MESSAGE(worst_raw > 30.0f, "noise injection is not injecting");
    // The filter must beat raw differentiation by a wide margin — §4's claim, asserted.
    TEST_ASSERT_TRUE_MESSAGE(worst_smoothed < 0.5f * worst_raw,
                             "smoothing is not beating raw dh/dt");
    // Usability bounds on the transmitted value (coast truth is 0..~515 ft/s):
    TEST_ASSERT_TRUE_MESSAGE(rms < 15.0f, "Vel RMS error exceeds 15 ft/s under noise");
    TEST_ASSERT_TRUE_MESSAGE(worst_smoothed < 40.0f,
                             "Vel worst-case error exceeds 40 ft/s under noise");
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
    RUN_TEST(test_noise_rejection_is_real_not_assumed);
    return UNITY_END();
}
