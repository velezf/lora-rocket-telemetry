#ifndef APOGEE_H
#define APOGEE_H

// Apogee / descent detection — pure, portable C++ (host-testable in `native`).
// Ported from the V1 reference apogee logic (Feather9x_TX_V1.2.6.ino):
// track running max altitude while ascending; the first reading that falls
// below the running max flags apogee, and descending latches thereafter.
//
// No <Arduino.h>, no RadioHead — safe for the dependency-free native env.

namespace apogee {

class Detector {
public:
    Detector() : max_altitude_(0.0f), descending_(false), seen_(false) {}

    // Feed one altitude reading. Returns true ONCE, at the moment apogee is
    // first detected (altitude drops below the running max after ascent).
    // Subsequent calls return false; descending stays latched.
    bool update(float altitude) {
        if (!seen_ || altitude > max_altitude_) {
            // Still ascending (or first sample): grow the peak.
            max_altitude_ = altitude;
            seen_ = true;
            return false;
        }
        // altitude <= running max: we have started (or continue) descending.
        if (!descending_) {
            descending_ = true;
            return true;  // apogee fires exactly once
        }
        return false;
    }

    float max_altitude() const { return max_altitude_; }
    bool is_descending() const { return descending_; }

private:
    float max_altitude_;
    bool descending_;
    bool seen_;  // has at least one sample been recorded?
};

}  // namespace apogee

#endif  // APOGEE_H
