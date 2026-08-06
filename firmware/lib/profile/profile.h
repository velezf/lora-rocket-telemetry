#ifndef PROFILE_H
#define PROFILE_H

// Synthetic flight-profile generator + detector harness (6.0b).
//
// THE MEASURING INSTRUMENT. Every latency claim in the telemetry-quality work is measured
// against this, not computed. It exists BEFORE the detector it measures, deliberately: you
// cannot validate hysteresis or dwell without a profile to run them against, and a claim
// like "20 Hz costs 27 ft where 1 Hz costs 257 ft" should be an OBSERVATION, not arithmetic.
//
// Pure, portable C++ — no <Arduino.h>, no RadioHead — so it runs in the `native` env
// alongside the units it exercises (the lib/ purity rule).
//
// The profile is deliberately SIMPLE physics: powered boost to burnout, then unpowered
// coast decelerating under gravity to apogee, then descent. It is not a simulation. Its job
// is to be a repeatable ruler with a KNOWN apogee time, so detector latency is measurable
// against ground truth rather than eyeballed.

namespace profile {

struct Params {
    float burn_s        = 1.6f;    // motor burn time
    float boost_accel_g = 12.0f;   // net upward accel during burn, in g
    float apogee_ft     = 0.0f;    // filled by generate(): ground truth
    float apogee_s      = 0.0f;    // filled by generate(): ground truth
};

// Altitude in feet at time t, for a profile with the given parameters.
// Ground truth is analytic, so apogee time/altitude are exact, not sampled.
inline float altitude_ft(const Params& p, float t) {
    const float g = 32.174f;
    const float a = p.boost_accel_g * g;          // net accel while burning
    if (t <= 0.0f) return 0.0f;
    if (t < p.burn_s) return 0.5f * a * t * t;    // powered
    const float v_bo = a * p.burn_s;              // burnout velocity
    const float h_bo = 0.5f * a * p.burn_s * p.burn_s;
    const float dt = t - p.burn_s;
    const float h = h_bo + v_bo * dt - 0.5f * g * dt * dt;
    return h > 0.0f ? h : 0.0f;
}

// Fill in the analytic ground truth (apogee time and altitude).
inline void generate(Params& p) {
    const float g = 32.174f;
    const float a = p.boost_accel_g * g;
    const float v_bo = a * p.burn_s;
    p.apogee_s  = p.burn_s + v_bo / g;            // coast until vertical velocity hits zero
    p.apogee_ft = altitude_ft(p, p.apogee_s);
}

// Result of running a detector over a sampled profile.
struct Result {
    bool  fired       = false;
    float fire_s      = 0.0f;     // when the detector declared apogee
    float latency_s   = 0.0f;     // fire_s - true apogee_s
    float fell_ft     = 0.0f;     // altitude LOST between true apogee and declaration
    float speed_fps   = 0.0f;     // vertical speed at declaration
    int   samples     = 0;
};

// Run `det` over the profile at `hz`, feeding altitude_ft() at each tick.
// `Det` must expose bool update(float altitude_ft).
//
// Sampling the SAME profile at different rates is the whole point: it isolates the cost of
// rate from the cost of the criterion, which is the question that decides whether decoupling
// sample rate from TX rate is worth doing.
template <typename Det>
Result run(Det& det, const Params& p, float hz, float until_s = 30.0f) {
    Result r;
    const float dt = 1.0f / hz;
    for (float t = 0.0f; t <= until_s; t += dt) {
        r.samples++;
        if (det.update(altitude_ft(p, t))) {
            r.fired     = true;
            r.fire_s    = t;
            r.latency_s = t - p.apogee_s;
            r.fell_ft   = p.apogee_ft - altitude_ft(p, t);
            r.speed_fps = 32.174f * (t - p.apogee_s);   // free-fall speed since apogee
            return r;
        }
    }
    return r;
}

}  // namespace profile

#endif  // PROFILE_H
