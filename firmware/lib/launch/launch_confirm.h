#ifndef LAUNCH_CONFIRM_H
#define LAUNCH_CONFIRM_H

// Confirmed launch detection — CONFIRM-OR-REVERT, pure and host-tested.
//
// WHY THIS EXISTS. LaunchDetector (launch.h) latches in-flight on a SINGLE sample crossing
// 3 g and never unlatches. One transient permanently changes the flight state, and every
// packet afterwards carries St:1 whether or not anything flew. There was no way back except
// a power cycle — on the pad, with an igniter already wired, at the worst possible moment.
//
// THE MEASUREMENT THAT SHAPED THIS (17 Hz, 59 ms/sample, synthetic profiles in lib/profile):
//
//   knock width      dwell=100 ms   dwell=300 ms
//   1-2 samples      reject         reject
//   3-6 samples      LAUNCH         reject          <- 177-354 ms: a real set-down
//   7+ samples       LAUNCH         LAUNCH
//
//   altitude gain    +0.5 s   +1.0 s   +2.0 s
//   A8 (smallest)     40 ft   117 ft   245 ft
//   F15               48 ft   193 ft   739 ft
//   handling           0 ft     0 ft     0 ft
//
// A dwell separates a knock from a launch by a FACTOR OF TWO. Altitude separates them by
// THREE ORDERS OF MAGNITUDE — you cannot lift a rocket 100 ft by hand. So the dwell is the
// weaker discriminator and tuning it was tuning the wrong knob. The accel gate's job is only
// to decide when to START looking at altitude; altitude decides whether it was a launch.
//
// THE STATE MACHINE:
//
//   ARMED --[g > threshold for dwell_ms]--> PROVISIONAL --[climbed confirm_ft]--> CONFIRMED
//                  ^                             |
//                  +--[confirm_ms elapsed]-------+   THE UN-LATCH
//
// ACCELERATION DROPPING OUT IS NOT A REVERT, and the harness had to teach me that. The first
// version reverted the moment g fell back below threshold, on the reasoning that a transient
// is over quickly. Measured against the profiles, an A8 (0.5 s burn) NEVER CONFIRMED: it
// reaches 50 ft at 0.557 s, so burnout arrives first, and the launch was thrown away at the
// instant the rocket started coasting. EVERY real launch drops below 3 g at burnout — that is
// what burnout IS. So the provisional state ends on TIME or on ALTITUDE, never on the
// accelerometer. Only the fallback still demands sustained acceleration, because without
// altitude that is the only evidence left.
//
// TWO CLOCKS BOUND THE PROVISIONAL STATE, and the second exists because the first can be
// postponed. confirm_ms runs from launch_ms_, which RE-ANCHORS on a new acceleration event --
// so acceleration oscillating across the threshold restarts the window every time and the
// provisional never expires. That is a permanent latch of exactly the kind this class was
// written to remove, just relocated. max_provisional_ms runs from the FIRST entry into
// PROVISIONAL and is never re-anchored, so the state is bounded no matter what the
// accelerometer does. Removing one latch is not licence to leave a different one behind.
//
// THE WINDOW IS DELIBERATELY GENEROUS, because the risk is asymmetric. A window too SHORT
// discards a real launch and the flight records St:0 throughout — unrecoverable. A window too
// LONG only means a false trigger sits in PROVISIONAL a little longer, and provisional is
// never published, so it costs nothing observable. When the two errors are that unequal, the
// constant belongs on the safe side of the trade.
//
// PROVISIONAL IS NOT PUBLISHED. is_in_flight() stays false until altitude confirms, so a
// false trigger never reaches the wire at all — St:1 is only ever emitted for something that
// actually climbed. The un-latch is the reverting edge: it has a DEFINED trigger (the window
// expired without the altitude gain) rather than being a timeout guess.
//
// MET IS BACKDATED. launch_ms() reports the FIRST above-threshold sample, not the moment of
// confirmation, so buying robustness with a confirmation window costs no MET accuracy. St:1
// arrives a beat late; MET zero does not move.
//
// THE FALLBACK, AND WHY IT USES THE STRICTER DWELL. This makes launch depend on the
// barometer, where before it depended only on the accelerometer — so a barometer failure
// during boost would mean launch never confirms. When altitude is unusable we fall back to
// accel-only, but at fallback_dwell_ms (300 ms) rather than dwell_ms (100 ms): we have lost
// the better discriminator, so the weaker one is tightened to compensate. The two knobs are
// complementary rather than redundant, and 300 ms finally has a job worth having.
//
// TWO BAROMETER FAILURES, ONE CONSEQUENCE, DIFFERENT EVIDENCE. A dead barometer (reads fail)
// and a STUCK barometer (reads succeed, value frozen) both report no altitude gain, so launch
// never confirms — but only the first moves a failure counter. The second is the
// silent-failure class: the fallback would never arm and the rocket would fly St:0 for the
// whole flight. So both are watched.
//
// They are NOT given the same threshold, because they are not equally strong evidence. A
// failed read is unambiguous: the sensor did not answer. A frozen value is ambiguous — a
// STATIONARY rocket on the pad genuinely can report the same altitude several samples running,
// and if that were enough to arm the fallback then a sustained knock on a quiet pad would be
// declared a launch with no altitude corroboration at all. So a frozen value must persist
// TWICE as long (frozen_ms) as a failed read (stale_ms) before it is believed. This costs
// nothing on a real flight: the smallest motor measured climbs 40 ft in half a second, so a
// live barometer cannot look frozen during boost.
//
// Constants are in TIME, not sample counts — the sled's achieved sample rate is a measured
// property of the BMP390 at its configured oversampling, not a number we choose. A dwell of
// "3 samples" means 3 s at 1 Hz and 0.15 s at 20 Hz; a dwell of 300 ms means 300 ms at any
// rate, and only the resolution changes. This is why the staleness check is also in time.

namespace launch {

class Confirm {
public:
    static constexpr float kDefaultThresholdG = 3.0f;

    // threshold_g        : sensed acceleration magnitude that arms the provisional launch.
    // dwell_ms           : how long it must hold before altitude starts being watched.
    // confirm_ft         : altitude gain above the provisional baseline that confirms.
    // confirm_ms         : how long the gain has to appear before the launch is REVERTED.
    //                      Generous on purpose — see the asymmetry note above.
    // fallback_dwell_ms  : accel-only dwell used when altitude is unusable (stricter).
    // stale_ms           : no SUCCESSFUL altitude read for this long => barometer dead.
    // frozen_ms          : reads succeed but the value has not MOVED this long => stuck.
    //                      Deliberately longer than stale_ms: weaker evidence, higher bar.
    // max_provisional_ms : absolute ceiling on PROVISIONAL, measured from first entry and
    //                      never re-anchored. The guarantee that the state cannot latch.
    explicit Confirm(float threshold_g            = kDefaultThresholdG,
                     unsigned long dwell_ms       = 100,
                     float confirm_ft             = 50.0f,
                     unsigned long confirm_ms     = 2000,
                     unsigned long fallback_dwell_ms = 300,
                     unsigned long stale_ms       = 300,
                     unsigned long frozen_ms      = 600,
                     unsigned long max_provisional_ms = 5000)
        : threshold_g_(threshold_g), dwell_ms_(dwell_ms), confirm_ft_(confirm_ft),
          confirm_ms_(confirm_ms), fallback_dwell_ms_(fallback_dwell_ms), stale_ms_(stale_ms),
          frozen_ms_(frozen_ms), max_provisional_ms_(max_provisional_ms),
          above_since_ms_(0), launch_ms_(0), provisional_since_ms_(0), last_valid_ms_(0),
          alt_moved_ms_(0), last_alt_ft_(0.0f), baseline_ft_(0.0f), reverts_(0), above_(false),
          provisional_(false), baseline_valid_(false), sustained_(false), in_flight_(false),
          used_fallback_(false) {}

    // Feed one sample: acceleration magnitude, altitude, whether that altitude READ SUCCEEDED,
    // and the monotonic timestamp. altitude_valid == false is the barometer failure counter
    // moving — the caller already tracks it, so no new signal is invented here.
    //
    // Returns true EXACTLY ONCE, when launch is CONFIRMED. Latches thereafter.
    bool update(float g, float altitude_ft, bool altitude_valid, unsigned long now_ms) {
        if (in_flight_) return false;

        const bool above = (g > threshold_g_);

        // Two clocks, because there are two failures. last_valid_ms_ answers "did the sensor
        // answer at all"; alt_moved_ms_ answers "did the answer change". A stuck barometer
        // keeps the first clock running and stops the second.
        if (altitude_valid) {
            last_valid_ms_ = now_ms;
            if (!baseline_valid_ || altitude_ft != last_alt_ft_) {
                last_alt_ft_  = altitude_ft;
                alt_moved_ms_ = now_ms;
            }
        }

        if (!provisional_) return arm(above, altitude_ft, altitude_valid, now_ms);

        // --- PROVISIONAL: altitude has to earn it ---

        // Burnout is not a failure. Acceleration falling away only disqualifies the FALLBACK,
        // which has nothing but acceleration to go on; the altitude path is unaffected.
        // NOTE: this must NOT return early. Falling out of thrust has to keep flowing into the
        // altitude check and the window check below, or burnout blocks confirmation again.
        if (!above) sustained_ = false;

        // A NEW ACCELERATION EVENT IS A NEW CANDIDATE LAUNCH. If acceleration dropped out and
        // has now returned, the event that opened this provisional is over, and leaving the
        // anchor where it was means MET is backdated to a transient that already ended --
        // measured at 472 ms wrong in the test that found this. Re-anchor instead.
        //
        // BUT ONLY IF NOTHING HAS HAPPENED YET. A real flight can dip below threshold mid-burn
        // on vibration, and re-anchoring THAT would push MET zero later on a genuine launch,
        // which is the worse error. So the climb already achieved decides: no meaningful gain
        // means the old anchor is worthless, and a gain means the flight is already underway
        // and the original anchor is the true one.
        else if (!sustained_) {
            const bool climbing = baseline_valid_ && (altitude_ft - baseline_ft_) >= confirm_ft_ / 2.0f;
            if (!climbing) {
                launch_ms_      = now_ms;
                baseline_valid_ = false;
                last_valid_ms_  = now_ms;
                alt_moved_ms_   = now_ms;
            }
            sustained_ = true;
        }

        // Late baseline: the barometer may have been failing when the gate opened.
        if (altitude_valid && !baseline_valid_) {
            baseline_ft_    = altitude_ft;
            baseline_valid_ = true;
        }

        // NORMAL PATH — the good discriminator.
        if (altitude_valid && baseline_valid_ &&
            (altitude_ft - baseline_ft_) >= confirm_ft_) {
            in_flight_ = true;
            return true;
        }

        // FALLBACK PATH — altitude unusable, so accel-only at the stricter dwell. The dwell
        // is measured from the BACKDATED launch instant, so it is a true span of sustained
        // acceleration rather than 300 ms after some later bookkeeping moment.
        const bool dead   = (now_ms - last_valid_ms_) >= stale_ms_;
        const bool frozen = (now_ms - alt_moved_ms_)  >= frozen_ms_;
        if (sustained_ && (dead || frozen) && (now_ms - launch_ms_) >= fallback_dwell_ms_) {
            in_flight_     = true;
            used_fallback_ = true;
            return true;
        }

        // THE UN-LATCH — no altitude gain in time. It was handling, not a launch. Either the
        // per-candidate window expired, or the absolute ceiling did; the ceiling is what makes
        // the state provably bounded even when re-anchoring keeps restarting the window.
        if ((now_ms - launch_ms_) >= confirm_ms_ ||
            (now_ms - provisional_since_ms_) >= max_provisional_ms_) revert();
        return false;
    }

    bool          is_in_flight()   const { return in_flight_; }
    bool          is_provisional() const { return provisional_; }
    // Backdated to the first above-threshold sample, so MET zero is the real launch instant.
    unsigned long launch_ms()      const { return launch_ms_; }
    // True when the launch was declared without altitude corroboration — the flight record
    // should be able to say the confirmation was degraded.
    bool          used_fallback()  const { return used_fallback_; }
    // How many provisional launches were reverted: a direct count of transients rejected.
    unsigned int  reverts()        const { return reverts_; }
    float         threshold_g()    const { return threshold_g_; }

private:
    bool arm(bool above, float altitude_ft, bool altitude_valid, unsigned long now_ms) {
        if (!above) { above_ = false; return false; }
        if (!above_) {
            above_ = true;
            above_since_ms_ = now_ms;
            if (dwell_ms_ != 0) return false;        // dwell 0 == legacy immediate arm
        }
        if ((now_ms - above_since_ms_) < dwell_ms_) return false;

        provisional_          = true;
        sustained_            = true;
        launch_ms_            = above_since_ms_;     // BACKDATE: first above-threshold sample
        provisional_since_ms_ = now_ms;              // ceiling clock: NEVER re-anchored
        baseline_valid_ = false;
        // Both clocks start at the BACKDATED instant, so a barometer that was already failing
        // when the gate opened is recognised without an extra grace period.
        last_valid_ms_  = launch_ms_;
        alt_moved_ms_   = launch_ms_;
        if (altitude_valid) {
            baseline_ft_    = altitude_ft;
            baseline_valid_ = true;
            last_alt_ft_    = altitude_ft;
            last_valid_ms_  = now_ms;
            alt_moved_ms_   = now_ms;
        }
        return false;                                // PROVISIONAL IS NEVER PUBLISHED
    }

    void revert() {
        provisional_    = false;
        baseline_valid_ = false;
        sustained_      = false;
        above_          = false;    // a fresh dwell must be served before re-arming
        launch_ms_      = 0;
        reverts_++;
    }

    float         threshold_g_;
    unsigned long dwell_ms_;
    float         confirm_ft_;
    unsigned long confirm_ms_;
    unsigned long fallback_dwell_ms_;
    unsigned long stale_ms_;
    unsigned long frozen_ms_;
    unsigned long max_provisional_ms_;
    unsigned long above_since_ms_;
    unsigned long launch_ms_;
    unsigned long provisional_since_ms_;
    unsigned long last_valid_ms_;
    unsigned long alt_moved_ms_;
    float         last_alt_ft_;
    float         baseline_ft_;
    unsigned int  reverts_;
    bool          above_;
    bool          provisional_;
    bool          baseline_valid_;
    bool          sustained_;
    bool          in_flight_;
    bool          used_fallback_;
};

}  // namespace launch

#endif  // LAUNCH_CONFIRM_H
