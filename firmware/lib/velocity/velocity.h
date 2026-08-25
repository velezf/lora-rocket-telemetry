#ifndef VELOCITY_H
#define VELOCITY_H

// Onboard vertical velocity — dh/dt at the sample rate with light smoothing (ADR 0005 §4).
//
// WHY ONBOARD. Velocity differentiated on the GROUND from 10 Hz `ALT` would be noise:
// differentiation amplifies quantisation, and the barometer's step is a meaningful fraction
// of the per-sample altitude change. Computed here at the ~20 Hz sample rate the curve is
// real — *derive where the data is dense, transmit the derivative*.
//
// THE FILTER IS A TIME CONSTANT, NOT A SAMPLE COUNT — the same discipline as
// apogee::Confirm's dwell: the achieved sample rate is a MEASURED property of the BMP390,
// not a chosen one, so "smooth over N samples" would be a different filter at every rate.
// An irregular-interval EMA (alpha = dt / (tau + dt)) means tau is tau at any rate, and a
// missed baro read just widens dt instead of silently changing the filter.
//
// Pure, portable C++ — no <Arduino.h> (lib/ purity rule). The caller supplies monotonic
// milliseconds; no clock is read here.

namespace velocity {

// Smoothing time constant. Sized for "light": coast decelerates at 1 g, so EMA lag costs
// ~g*tau ≈ 6.4 ft/s at 200 ms (bounded by test_tracks_coast_phase_within_tolerance);
// during a 12 g boost the lag is ~a*tau, which is why the peak-capture test allows 15 %.
static const unsigned long DEFAULT_TAU_MS = 200;

class Estimator {
public:
    explicit Estimator(unsigned long tau_ms = DEFAULT_TAU_MS)
        : tau_ms_(tau_ms), prev_alt_ft_(0.0f), prev_ms_(0),
          vel_fps_(0.0f), primed_(false), has_(false) {}

    // Feed one altitude sample with its monotonic timestamp. Call ONLY on a successful
    // baro read: a failed read must widen dt, not inject a stale altitude as fresh.
    void update(float alt_ft, unsigned long now_ms) {
        if (!primed_) {                       // one point has no slope
            prev_alt_ft_ = alt_ft;
            prev_ms_     = now_ms;
            primed_      = true;
            return;
        }
        const unsigned long dt_ms = now_ms - prev_ms_;
        if (dt_ms == 0) return;               // no interval: nothing to divide by

        const float dt_s   = dt_ms / 1000.0f;
        const float v_raw  = (alt_ft - prev_alt_ft_) / dt_s;
        // Irregular-interval EMA: alpha derives from THIS interval, so the time constant
        // holds whether samples arrive at 10 Hz, 40 Hz, or with a gap in the middle.
        const float alpha  = dt_ms / (float)(tau_ms_ + dt_ms);
        vel_fps_ = has_ ? vel_fps_ + alpha * (v_raw - vel_fps_) : v_raw;

        prev_alt_ft_ = alt_ft;
        prev_ms_     = now_ms;
        has_         = true;
    }

    // Smoothed vertical velocity, ft/s. 0.0 until two samples have been seen (has()).
    float vel_fps() const { return has_ ? vel_fps_ : 0.0f; }
    bool  has() const { return has_; }

private:
    unsigned long tau_ms_;
    float         prev_alt_ft_;
    unsigned long prev_ms_;
    float         vel_fps_;
    bool          primed_;   // first sample stored
    bool          has_;      // a slope exists
};

}  // namespace velocity

#endif  // VELOCITY_H
