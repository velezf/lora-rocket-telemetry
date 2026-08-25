// BENCH BUILD flag semantics. BENCH_FORCE_FAST_TX exists for exactly one purpose:
// the A1.6 sustained-10 Hz bench cannot honestly be run on the flight build, because
// the flight build transmits fast only in confirmed flight — which a bench cannot
// induce without changing what is being measured. The flag forces the fast interval
// UNCONDITIONALLY so the RF path, loop and ground pipeline run at 10 Hz on the pad.
//
// The macro is defined ONLY by the feather_m0_tx_bench PlatformIO env (and by this
// test, locally, before the include — header-only unit, so the macro governs). The
// flight env and the native test env never define it; test_txsched next door pins
// the normal schedule, so a globally-leaked define would fail THAT suite loudly.
#define BENCH_FORCE_FAST_TX
#include <unity.h>
#include "txsched.h"

void setUp(void) {}
void tearDown(void) {}

using txsched::interval_ms;
using txsched::FLIGHT_TX_MS;
using txsched::FAST_WINDOW_MS;

// Under the flag the schedule is fast EVERYWHERE the flight build would be slow —
// on the pad, and beyond the MET bound. (The whole run, not an instant.)
void test_bench_flag_forces_fast_on_the_pad(void) {
    TEST_ASSERT_EQUAL_UINT32(FLIGHT_TX_MS, interval_ms(false, 0, 0));
    TEST_ASSERT_EQUAL_UINT32(FLIGHT_TX_MS, interval_ms(false, 123456789UL, 0));
}

void test_bench_flag_forces_fast_past_the_met_bound(void) {
    for (unsigned long met = 0; met <= 3UL * FAST_WINDOW_MS; met += 5000) {
        TEST_ASSERT_EQUAL_UINT32(FLIGHT_TX_MS, interval_ms(true, 1000 + met, 1000));
    }
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_bench_flag_forces_fast_on_the_pad);
    RUN_TEST(test_bench_flag_forces_fast_past_the_met_bound);
    return UNITY_END();
}
