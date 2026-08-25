#include <unity.h>
#include "txsched.h"

void setUp(void) {}
void tearDown(void) {}

using txsched::interval_ms;
using txsched::PAD_TX_MS;
using txsched::FLIGHT_TX_MS;
using txsched::FAST_WINDOW_MS;

// --- pad: slow, unconditionally ---

void test_pad_is_slow_regardless_of_clocks(void) {
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS, interval_ms(false, 0, 0));
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS, interval_ms(false, 123456789UL, 0));
    // a stale launch_ms from a reverted provisional must not leak speed onto the pad
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS, interval_ms(false, 5000, 4000));
}

// --- flight: fast inside the MET window ---

void test_flight_inside_window_is_fast(void) {
    TEST_ASSERT_EQUAL_UINT32(FLIGHT_TX_MS, interval_ms(true, 1000, 1000));   // MET 0
    TEST_ASSERT_EQUAL_UINT32(FLIGHT_TX_MS,
                             interval_ms(true, 1000 + FAST_WINDOW_MS - 1, 1000));
}

// --- THE BOUND (the reason this unit exists): flight states latch and there is no
// St:3, so "fast while in flight" would transmit at 58.9 % duty until the battery
// died in the recovery grass. The ONLY exit is MET, and it must actually exit. ---

void test_flight_past_window_reverts_to_slow(void) {
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS,
                             interval_ms(true, 1000 + FAST_WINDOW_MS, 1000));      // boundary
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS,
                             interval_ms(true, 1000 + FAST_WINDOW_MS + 1, 1000));
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS,
                             interval_ms(true, 1000 + 10UL * FAST_WINDOW_MS, 1000)); // hours later
}

// --- the QUANTIFIER, not an instant (evidence-trust pattern #5: "slow right now" is a
// proxy; the property is "fast EXACTLY when MET < window, for the whole run") ---

void test_fast_exactly_while_met_below_window_over_the_whole_run(void) {
    const unsigned long launch = 7000;
    for (unsigned long met = 0; met <= 3UL * FAST_WINDOW_MS; met += 100) {
        const unsigned long expect = (met < FAST_WINDOW_MS) ? FLIGHT_TX_MS : PAD_TX_MS;
        TEST_ASSERT_EQUAL_UINT32(expect, interval_ms(true, launch + met, launch));
    }
}

// --- the window is anchored to launch_ms (true MET zero, backdated to the accel gate),
// never to the first query — a first call arriving late must already be slow. Pins the
// CONTRACT so a future stateful rewrite cannot reintroduce the re-anchor class. ---

void test_window_measured_from_launch_not_first_query(void) {
    TEST_ASSERT_EQUAL_UINT32(PAD_TX_MS,
                             interval_ms(true, 1000 + FAST_WINDOW_MS + 5000, 1000));
}

// --- millis() wrap: the monotonic-delta idiom must survive now < launch_ms ---

void test_survives_millis_wrap(void) {
    const unsigned long launch = 0xFFFFFF00UL;       // just before wrap
    const unsigned long now    = 0x00000064UL;       // 100 ms after wrap -> MET 356 ms
    TEST_ASSERT_EQUAL_UINT32(FLIGHT_TX_MS, interval_ms(true, now, launch));
}

// --- constants sanity: the schedule's relationships, stated as claims that can fail ---

void test_constant_relationships(void) {
    // fast must be 10 Hz per ADR 0005, and slower than the txgate stuck bound is NOT
    // required — but the fast interval must exceed the worst BW500 time-on-air (~59 ms),
    // or every second frame would be a guaranteed SKIP by construction.
    TEST_ASSERT_EQUAL_UINT32(100, FLIGHT_TX_MS);
    TEST_ASSERT_TRUE(FLIGHT_TX_MS > 59);
    TEST_ASSERT_EQUAL_UINT32(1000, PAD_TX_MS);
    TEST_ASSERT_TRUE(FAST_WINDOW_MS >= 145000UL);   // >= worst realistic flight (see header)
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_pad_is_slow_regardless_of_clocks);
    RUN_TEST(test_flight_inside_window_is_fast);
    RUN_TEST(test_flight_past_window_reverts_to_slow);
    RUN_TEST(test_fast_exactly_while_met_below_window_over_the_whole_run);
    RUN_TEST(test_window_measured_from_launch_not_first_query);
    RUN_TEST(test_survives_millis_wrap);
    RUN_TEST(test_constant_relationships);
    return UNITY_END();
}
