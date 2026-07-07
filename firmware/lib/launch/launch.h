#ifndef LAUNCH_H
#define LAUNCH_H

// Pure, portable C++ launch detector for the sled TX (Epic 3.5).
// No <Arduino.h>, no RadioHead — host-testable in the `native` env.
//
// Ported from the V1 firmware behaviour:
//   if (!inFlight && g > launchThresholdG) { inFlight = true; ... }
// with a strict greater-than comparison and a default threshold of 3.0 g.

class LaunchDetector {
public:
    static constexpr float kDefaultThresholdG = 3.0f;

    explicit LaunchDetector(float threshold_g = kDefaultThresholdG)
        : threshold_g_(threshold_g), in_flight_(false) {}

    // Feed the latest measured acceleration magnitude (g).
    // Returns true ONLY at the moment launch is first detected
    // (transition from grounded to in-flight). Latches thereafter:
    // once in flight, always returns false regardless of g.
    bool update(float g) {
        if (!in_flight_ && g > threshold_g_) {
            in_flight_ = true;
            return true;
        }
        return false;
    }

    bool is_in_flight() const { return in_flight_; }

    float threshold_g() const { return threshold_g_; }

private:
    float threshold_g_;
    bool in_flight_;
};

#endif  // LAUNCH_H
