#ifndef LAUNCH_CONFIRM_H
#define LAUNCH_CONFIRM_H

// Confirmed launch detection — threshold + dwell, pure and host-tested.
//
// WHY THIS EXISTS. LaunchDetector (launch.h) latches in-flight on a SINGLE sample crossing
// 3 g and never unlatches. That is the same defect as the old apogee detector, mirrored:
// one transient permanently changes the flight state, and every packet afterwards carries
// St:1 whether or not anything flew.
//
// THE 20 Hz SAMPLING CHANGE MAKES IT MATERIALLY WORSE, which is the whole reason this
// landed alongside it. At 1 Hz a knock had roughly a one-in-twenty chance of coinciding with
// the sampling instant. At 20 Hz the sled samples every 50 ms, so ANY transient wider than
// ~50 ms is caught — and a hand-knock is 10-100 ms. The rate increase was justified by
// "catch the 2.2 g jerk the 2026-07-08 shake test missed"; the honest reading of that is
// that it now also reliably catches setting the sled down. A false launch on the pad while
// the operator is still wiring an igniter opens a flight that then has to be unpicked, at
// the worst possible moment.
//
// LAUNCH HAS AN ASYMMETRY APOGEE DOES NOT, and it is what makes dwell nearly free here: a
// real launch is SUSTAINED. An L1 motor pulls multiple g for 1.5+ seconds, while a knock is
// a spike. So a short dwell discriminates almost perfectly.
//
// 100 ms was chosen so the fix cannot cost a real detection: at 20 Hz it is 2 consecutive
// samples; at 1 Hz it degrades to exactly today's single-sample behaviour rather than
// breaking. The latency cost is ~100 ms on MET zero, and MET is transmitted in WHOLE
// SECONDS, so it rounds away entirely.
//
// Constants are in TIME, not sample counts — same discipline as apogee::Confirm, and for
// the same reason: the sled's achieved sample rate is a measured property of the hardware,
// not a number we choose.

namespace launch {

class Confirm {
public:
    static constexpr float kDefaultThresholdG = 3.0f;

    explicit Confirm(float threshold_g = kDefaultThresholdG, unsigned long dwell_ms = 100)
        : threshold_g_(threshold_g), dwell_ms_(dwell_ms),
          above_since_ms_(0), above_(false), in_flight_(false) {}

    // Feed the latest acceleration magnitude with its monotonic timestamp.
    // Returns true EXACTLY ONCE, when launch is confirmed. Latches thereafter.
    bool update(float g, unsigned long now_ms) {
        if (in_flight_) return false;

        if (g <= threshold_g_) {
            above_ = false;                     // dropped back: a spike, not a launch
            return false;
        }
        if (!above_) {                          // first sample above: start the dwell
            above_ = true;
            above_since_ms_ = now_ms;
            // A dwell of 0 means "fire immediately", preserving the legacy behaviour for
            // anyone who wants it; otherwise the first sample never fires on its own.
            if (dwell_ms_ == 0) { in_flight_ = true; return true; }
            return false;
        }
        if (now_ms - above_since_ms_ >= dwell_ms_) {
            in_flight_ = true;
            return true;
        }
        return false;
    }

    bool  is_in_flight() const { return in_flight_; }
    float threshold_g() const { return threshold_g_; }

private:
    float         threshold_g_;
    unsigned long dwell_ms_;
    unsigned long above_since_ms_;
    bool          above_;
    bool          in_flight_;
};

}  // namespace launch

#endif  // LAUNCH_CONFIRM_H
