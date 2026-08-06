#ifndef APOGEE_CONFIRM_H
#define APOGEE_CONFIRM_H

// Confirmed apogee detection (6.0c) — hysteresis + dwell, pure and host-tested.
//
// WHY THIS EXISTS. apogee::Detector (apogee.h) declares apogee on the FIRST sample that is
// not strictly greater than the running max, and latches permanently. One noisy sample
// during boost latches St:2 for the rest of the flight, and every packet after it carries a
// wrong flight state. That is a DATA-QUALITY defect: the flight record says "descending"
// through the entire ascent and no amount of ground-side derivation can recover the truth.
// (It was also a deployment hazard when a relay was planned; that plan is archived, and this
// is now a record-integrity fix, which is a smaller claim and the honest one.)
//
// TWO CONDITIONS, BOTH REQUIRED:
//   HYSTERESIS — altitude must fall at least `drop_ft` BELOW the running max. Sensor noise
//                of a few feet can no longer declare apogee.
//   DWELL      — that condition must hold continuously for `dwell_s`. A single spurious low
//                reading is rejected; a real descent persists.
//
// CONSTANTS ARE IN TIME, NOT SAMPLE COUNTS. This is deliberate and load-bearing: the sled's
// achieved sample rate is a measured property of the BMP390 at its configured oversampling,
// not a number we get to choose. A dwell of "3 samples" means 3 s at 1 Hz and 0.15 s at
// 20 Hz — the same code with wildly different behaviour. A dwell of 0.30 s means 0.30 s at
// any rate; only the RESOLUTION changes. So a slower-than-hoped sample rate degrades
// precision instead of silently redefining the criterion.
//
// The caller supplies monotonic milliseconds. No clock is read here — same discipline as the
// ground-side pure units, so this is testable against a synthetic profile at any rate.

namespace apogee {

class Confirm {
public:
    // drop_ft: how far below the running max before descent is even considered.
    // dwell_ms: how long that must hold continuously before apogee is declared.
    Confirm(float drop_ft = 20.0f, unsigned long dwell_ms = 300)
        : drop_ft_(drop_ft), dwell_ms_(dwell_ms),
          max_altitude_(0.0f), below_since_ms_(0), seen_(false),
          below_(false), descending_(false) {}

    // Feed one altitude reading with its monotonic timestamp.
    // Returns true EXACTLY ONCE, when apogee is confirmed. Latches thereafter.
    bool update(float altitude_ft, unsigned long now_ms) {
        if (descending_) return false;

        if (!seen_ || altitude_ft > max_altitude_) {
            max_altitude_ = altitude_ft;
            seen_  = true;
            below_ = false;                       // any new high resets the dwell
            return false;
        }
        if (altitude_ft > max_altitude_ - drop_ft_) {
            below_ = false;                       // inside the noise band: not descending
            return false;
        }
        if (!below_) {                            // first sample below the band: start dwell
            below_ = true;
            below_since_ms_ = now_ms;
            return false;
        }
        if (now_ms - below_since_ms_ >= dwell_ms_) {
            descending_ = true;
            return true;
        }
        return false;
    }

    float max_altitude() const { return max_altitude_; }
    bool  is_descending() const { return descending_; }

private:
    float         drop_ft_;
    unsigned long dwell_ms_;
    float         max_altitude_;
    unsigned long below_since_ms_;
    bool          seen_;
    bool          below_;
    bool          descending_;
};

}  // namespace apogee

#endif  // APOGEE_CONFIRM_H
