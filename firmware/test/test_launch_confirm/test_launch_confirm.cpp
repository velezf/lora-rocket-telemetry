#include <unity.h>
#include "launch.h"
#include "launch_confirm.h"

void setUp(void) {}
void tearDown(void) {}

// The sled's MEASURED sample period. Using the real number rather than the 50 ms target means
// these tests exercise the timing the firmware actually runs at.
static const unsigned long DT = 59;

// --- the defect, stated as a test so it cannot be argued about ---

void test_old_detector_latches_on_a_single_knock(void) {
    LaunchDetector d;
    TEST_ASSERT_TRUE(d.update(4.0f));       // ONE sample over threshold: in flight, forever
    TEST_ASSERT_TRUE(d.is_in_flight());
    d.update(1.0f); d.update(1.0f);         // back on the bench, motionless
    TEST_ASSERT_TRUE(d.is_in_flight());     // still "flying", and no way back but a power cycle
}

// --- PROVISIONAL IS NOT PUBLISHED: the accel gate alone never reaches the wire ---

void test_the_accel_gate_alone_does_not_report_in_flight(void) {
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 6; i++) { c.update(8.0f, 100.0f, true, t); t += DT; }
    TEST_ASSERT_TRUE(c.is_provisional());       // gate opened...
    TEST_ASSERT_FALSE(c.is_in_flight());        // ...but nothing is claimed yet
}

// --- the normal path: altitude is what actually confirms ---

void test_a_real_climb_confirms_and_fires_exactly_once(void) {
    launch::Confirm c;
    unsigned long t = 0;
    int fires = 0;
    float alt = 0.0f;
    for (int i = 0; i < 40; i++) {
        alt = 0.5f * (10.0f * 32.174f) * (t / 1000.0f) * (t / 1000.0f);   // A8-like boost
        if (c.update(11.0f, alt, true, t)) fires++;
        t += DT;
    }
    TEST_ASSERT_EQUAL_INT(1, fires);
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_FALSE(c.used_fallback());       // altitude did the work, not the fallback
    TEST_ASSERT_EQUAL_UINT32(0, c.reverts());
}

void test_met_is_backdated_to_the_first_above_threshold_sample(void) {
    // The confirmation window must not cost MET accuracy: t0 is the accel gate, not the
    // moment altitude agreed.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 3; i++) { c.update(1.0f, 0.0f, true, t); t += DT; }   // quiet first
    const unsigned long gate = t;                                            // boost starts here
    float alt = 0.0f;
    for (int i = 0; i < 40; i++) {
        const float dt_s = (t - gate) / 1000.0f;
        alt = 0.5f * (10.0f * 32.174f) * dt_s * dt_s;
        if (c.update(11.0f, alt, true, t)) break;
        t += DT;
    }
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_EQUAL_UINT32(gate, c.launch_ms());   // backdated, NOT the confirmation time
    TEST_ASSERT_TRUE(t > gate);                      // and confirmation really was later
}

// --- THE UN-LATCH: a 3 g transient with no climb is handling, not a launch ---

void test_a_sustained_3g_transient_with_no_climb_REVERTS(void) {
    launch::Confirm c;
    unsigned long t = 0;
    bool fired = false;
    // 3 s of above-threshold acceleration, barometer alive and noisy, but going nowhere.
    for (int i = 0; i < 52; i++) {
        const float alt = (i % 2) ? 100.1f : 100.0f;   // alive and moving, just not climbing
        if (c.update(8.0f, alt, true, t)) fired = true;
        t += DT;
    }
    TEST_ASSERT_FALSE(fired);
    TEST_ASSERT_FALSE(c.is_in_flight());
    TEST_ASSERT_TRUE(c.reverts() >= 1);       // it un-latched, which the old code could not
}

// --- THE REGRESSION THE HARNESS FOUND: burnout must not throw the launch away ---

void test_BURNOUT_does_not_revert_a_short_burn_launch(void) {
    // An A8 burns 0.5 s but does not clear 50 ft until 0.557 s. An earlier version reverted
    // the moment acceleration fell back below threshold, so this flight NEVER CONFIRMED.
    // Every real launch drops below 3 g at burnout -- that is what burnout is.
    launch::Confirm c;
    unsigned long t = 0;
    bool fired = false;
    for (int i = 0; i < 60; i++) {
        const float ts  = t / 1000.0f;
        const float acc = 10.0f * 32.174f;
        const float g   = (ts < 0.5f) ? 11.0f : 0.2f;              // thrust, then coasting
        const float alt = (ts < 0.5f) ? 0.5f * acc * ts * ts
                                      : 0.5f * acc * 0.25f + acc * 0.5f * (ts - 0.5f)
                                        - 0.5f * 32.174f * (ts - 0.5f) * (ts - 0.5f);
        if (c.update(g, alt, true, t)) fired = true;
        t += DT;
    }
    TEST_ASSERT_TRUE(fired);
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_EQUAL_UINT32(0, c.launch_ms());   // backdated to the very first sample
    TEST_ASSERT_EQUAL_UINT32(0, c.reverts());
}

void test_accel_dropout_disqualifies_only_the_FALLBACK(void) {
    // Losing acceleration cannot revert a launch, but it must stop the accel-only fallback:
    // that path has nothing but acceleration to go on, so it needs the real thing.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 3; i++) { c.update(8.0f, 0.0f, false, t); t += DT; }   // baro dead
    TEST_ASSERT_TRUE(c.is_provisional());
    for (int i = 0; i < 40; i++) {                          // put it down, past the window
        if (c.update(1.0f, 0.0f, false, t)) TEST_FAIL_MESSAGE("fallback fired after dropout");
        t += DT;
    }
    TEST_ASSERT_FALSE(c.is_in_flight());
    TEST_ASSERT_TRUE(c.reverts() >= 1);           // the window expired instead
}

void test_after_a_revert_a_REAL_launch_is_still_detected(void) {
    // The un-latch is worthless if it leaves the detector deaf afterwards.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 52; i++) {           // false trigger, reverts
        if (c.update(8.0f, (i % 2) ? 100.1f : 100.0f, true, t)) TEST_FAIL_MESSAGE("false launch");
        t += DT;
    }
    TEST_ASSERT_FALSE(c.is_in_flight());
    for (int i = 0; i < 10; i++) { c.update(1.0f, 100.0f, true, t); t += DT; }   // settles

    const unsigned long gate = t;            // now fly it for real
    bool fired = false;
    for (int i = 0; i < 40; i++) {
        const float dt_s = (t - gate) / 1000.0f;
        const float alt = 100.0f + 0.5f * (10.0f * 32.174f) * dt_s * dt_s;
        if (c.update(11.0f, alt, true, t)) fired = true;
        t += DT;
    }
    TEST_ASSERT_TRUE(fired);
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_EQUAL_UINT32(gate, c.launch_ms());   // and MET is the SECOND gate, not the first
}

void test_a_stale_provisional_does_not_steal_MET_from_a_real_launch(void) {
    // Found by the test above. A provisional still pending when the real boost starts used to
    // keep its old anchor, so MET zero was backdated to a transient that had already ended.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 8; i++) { c.update(8.0f, 100.0f, true, t); t += DT; }   // false trigger
    TEST_ASSERT_TRUE(c.is_provisional());
    for (int i = 0; i < 4; i++) { c.update(1.0f, 100.0f, true, t); t += DT; }   // and it ends
    TEST_ASSERT_TRUE(c.is_provisional());        // window has NOT expired yet

    const unsigned long gate = t;                // the real launch begins here
    for (int i = 0; i < 40; i++) {
        const float dt_s = (t - gate) / 1000.0f;
        const float alt = 100.0f + 0.5f * (10.0f * 32.174f) * dt_s * dt_s;
        if (c.update(11.0f, alt, true, t)) break;
        t += DT;
    }
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_EQUAL_UINT32(gate, c.launch_ms());   // the NEW event, not the stale one
}

void test_a_mid_burn_dip_does_NOT_move_MET_zero(void) {
    // The other side of the same trade: once the rocket is genuinely climbing, a momentary dip
    // below threshold must not re-anchor MET later. The climb already achieved is the evidence.
    launch::Confirm c;
    unsigned long t = 0;
    const unsigned long gate = 0;
    for (int i = 0; i < 40; i++) {
        const float dt_s = t / 1000.0f;
        const float alt = 0.5f * (10.0f * 32.174f) * dt_s * dt_s;
        const float g   = (i == 12) ? 1.0f : 11.0f;          // one vibration dip mid-burn
        if (c.update(g, alt, true, t)) break;
        t += DT;
    }
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_EQUAL_UINT32(gate, c.launch_ms());
}

void test_prolonged_shaking_never_launches(void) {
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 255; i++) {          // 15 s of vigorous handling
        if (c.update(9.0f, (i % 2) ? 12.0f : 12.5f, true, t)) TEST_FAIL_MESSAGE("false launch");
        t += DT;
    }
    TEST_ASSERT_FALSE(c.is_in_flight());
    TEST_ASSERT_TRUE(c.reverts() >= 2);      // it kept rejecting, repeatedly
}

// --- WE REMOVED ONE LATCH; PROVE WE DID NOT LEAVE ANOTHER ---

void test_a_provisional_can_NEVER_stay_pending_forever(void) {
    // With accel dropout no longer reverting, the confirm window is the ONLY revert path --
    // so it must not be possible to postpone it indefinitely. Oscillating acceleration with no
    // climb re-anchors on every rising edge, and each re-anchor restarts the window.
    // The property is BOUNDEDNESS, not the state at some arbitrary instant: the detector may
    // legitimately re-enter PROVISIONAL straight after reverting. So measure the longest
    // CONTINUOUS run and require it to respect the ceiling.
    launch::Confirm c;
    unsigned long t = 0;
    unsigned long run_start = 0, longest_run = 0;
    bool was_provisional = false;
    for (int i = 0; i < 1700; i++) {          // 100 s of thrashing, never climbing
        const float g = (i % 6 < 3) ? 8.0f : 1.0f;   // crosses the threshold every ~180 ms
        if (c.update(g, 100.0f + (i % 2) * 0.1f, true, t)) TEST_FAIL_MESSAGE("false launch");
        if (c.is_provisional() && !was_provisional) run_start = t;
        if (!c.is_provisional() && was_provisional && (t - run_start) > longest_run)
            longest_run = t - run_start;
        was_provisional = c.is_provisional();
        t += DT;
    }
    TEST_ASSERT_FALSE(c.is_in_flight());
    TEST_ASSERT_TRUE(longest_run > 0);                 // it really did enter PROVISIONAL
    TEST_ASSERT_TRUE(longest_run <= 5000 + DT);        // and never sat there past the ceiling
    TEST_ASSERT_TRUE(c.reverts() >= 15);               // 100 s / 5 s ceiling: it kept giving up
}

// --- THE FALLBACK: a dead barometer must not ground the launch detector ---

void test_a_DEAD_barometer_falls_back_to_accel_only_at_the_stricter_dwell(void) {
    launch::Confirm c;
    unsigned long t = 0;
    unsigned long fired_at = 0;
    for (int i = 0; i < 20; i++) {
        if (c.update(8.0f, 0.0f, false, t)) { fired_at = t; break; }   // every read FAILS
        t += DT;
    }
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_TRUE(c.used_fallback());          // the record can say it was degraded
    TEST_ASSERT_TRUE(fired_at >= 300);            // 300 ms fallback dwell, not the 100 ms one
}

void test_the_DEAD_barometer_fallback_still_rejects_a_short_knock(void) {
    // Losing the barometer must not turn every knock into a launch: 100 ms would have fired,
    // 300 ms does not.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 4; i++) {                 // ~236 ms of knock, baro dead
        if (c.update(8.0f, 0.0f, false, t)) TEST_FAIL_MESSAGE("knock launched on fallback");
        t += DT;
    }
    for (int i = 0; i < 10; i++) {
        if (c.update(1.0f, 0.0f, false, t)) TEST_FAIL_MESSAGE("knock launched on fallback");
        t += DT;
    }
    TEST_ASSERT_FALSE(c.is_in_flight());
}

// --- THE SILENT ONE: a barometer that reads fine but never changes ---

void test_a_STUCK_barometer_is_treated_as_unavailable(void) {
    // Reads all SUCCEED, so the failure counter never moves. Without a staleness check the
    // fallback would never arm and the rocket would fly St:0 for the whole flight.
    launch::Confirm c;
    unsigned long t = 0;
    unsigned long fired_at = 0;
    for (int i = 0; i < 30; i++) {
        if (c.update(8.0f, 137.0f, true, t)) { fired_at = t; break; }   // frozen value
        t += DT;
    }
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_TRUE(c.used_fallback());
    TEST_ASSERT_TRUE(fired_at >= 600);        // frozen must persist longer than dead
}

void test_a_stuck_barometer_needs_LONGER_than_a_dead_one_before_the_fallback(void) {
    // A stationary rocket can legitimately report the same altitude for a few samples, so a
    // frozen reading is weaker evidence than a failed read. A ~400 ms knock on a quiet pad
    // must NOT be promoted to a launch.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 7; i++) {                 // ~413 ms of knock, baro reading steadily
        if (c.update(8.0f, 137.0f, true, t)) TEST_FAIL_MESSAGE("quiet-pad knock launched");
        t += DT;
    }
    for (int i = 0; i < 10; i++) {
        if (c.update(1.0f, 137.0f, true, t)) TEST_FAIL_MESSAGE("quiet-pad knock launched");
        t += DT;
    }
    TEST_ASSERT_FALSE(c.is_in_flight());
}

void test_a_climbing_barometer_never_looks_frozen(void) {
    // The frozen check must not fire on a real flight — the confirmation must come from the
    // altitude gain, with used_fallback() false.
    launch::Confirm c;
    unsigned long t = 0;
    for (int i = 0; i < 40; i++) {
        const float dt_s = t / 1000.0f;
        const float alt = 0.5f * (8.0f * 32.174f) * dt_s * dt_s;   // slowest profile measured
        if (c.update(9.0f, alt, true, t)) break;
        t += DT;
    }
    TEST_ASSERT_TRUE(c.is_in_flight());
    TEST_ASSERT_FALSE(c.used_fallback());
}

// --- constants are TIME, so a slower achieved rate degrades resolution, not criteria ---

void test_the_criteria_hold_at_1hz(void) {
    launch::Confirm c;
    unsigned long t = 0;
    bool fired = false;
    for (int i = 0; i < 10; i++) {
        const float dt_s = t / 1000.0f;
        const float alt = 0.5f * (10.0f * 32.174f) * dt_s * dt_s;
        if (c.update(11.0f, alt, true, t)) { fired = true; break; }
        t += 1000;                                  // one sample per second
    }
    TEST_ASSERT_TRUE(fired);
    TEST_ASSERT_TRUE(c.is_in_flight());
}

void test_threshold_is_strictly_greater_than(void) {
    launch::Confirm c(3.0f, 0);                     // dwell 0 == arm on the first sample
    TEST_ASSERT_FALSE(c.update(3.0f, 0.0f, true, 0));
    TEST_ASSERT_FALSE(c.is_provisional());          // exactly at threshold is not a launch
    c.update(3.1f, 0.0f, true, DT);
    TEST_ASSERT_TRUE(c.is_provisional());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_old_detector_latches_on_a_single_knock);
    RUN_TEST(test_the_accel_gate_alone_does_not_report_in_flight);
    RUN_TEST(test_a_real_climb_confirms_and_fires_exactly_once);
    RUN_TEST(test_met_is_backdated_to_the_first_above_threshold_sample);
    RUN_TEST(test_a_sustained_3g_transient_with_no_climb_REVERTS);
    RUN_TEST(test_BURNOUT_does_not_revert_a_short_burn_launch);
    RUN_TEST(test_accel_dropout_disqualifies_only_the_FALLBACK);
    RUN_TEST(test_after_a_revert_a_REAL_launch_is_still_detected);
    RUN_TEST(test_a_stale_provisional_does_not_steal_MET_from_a_real_launch);
    RUN_TEST(test_a_mid_burn_dip_does_NOT_move_MET_zero);
    RUN_TEST(test_prolonged_shaking_never_launches);
    RUN_TEST(test_a_provisional_can_NEVER_stay_pending_forever);
    RUN_TEST(test_a_DEAD_barometer_falls_back_to_accel_only_at_the_stricter_dwell);
    RUN_TEST(test_the_DEAD_barometer_fallback_still_rejects_a_short_knock);
    RUN_TEST(test_a_STUCK_barometer_is_treated_as_unavailable);
    RUN_TEST(test_a_stuck_barometer_needs_LONGER_than_a_dead_one_before_the_fallback);
    RUN_TEST(test_a_climbing_barometer_never_looks_frozen);
    RUN_TEST(test_the_criteria_hold_at_1hz);
    RUN_TEST(test_threshold_is_strictly_greater_than);
    return UNITY_END();
}
