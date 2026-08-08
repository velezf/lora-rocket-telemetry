#include <unity.h>
#include "txgate.h"

void setUp(void) {}
void tearDown(void) {}

// The TX gate decides, each TX tick, between SEND / SKIP / FORCE_IDLE_SEND, given only
// (radio_busy, now_ms). Pure and host-tested; the radio and seq bookkeeping stay in src/.
//
// POLICY (Phase 2 item 3, decided and tested here):
//   - radio idle           -> SEND. Frames are rebuilt fresh each tick, so there is no
//                             queue: "send now" always means current data.
//   - busy, within timeout -> SKIP and count. The caller must NOT increment SEQ — a
//                             scheduling decision must not be published as RF loss.
//   - busy past timeout    -> the TxDone interrupt was missed (the unbounded
//                             waitPacketSent hang, relocated): FORCE_IDLE_SEND, count.

void test_idle_radio_sends_immediately(void) {
    txgate::Gate g;
    TEST_ASSERT_EQUAL(txgate::SEND, g.update(false, 0));
}

void test_busy_radio_skips_and_counts(void) {
    txgate::Gate g(500);
    TEST_ASSERT_EQUAL(txgate::SEND, g.update(false, 0));      // TX starts
    TEST_ASSERT_EQUAL(txgate::SKIP, g.update(true, 100));     // still on air at next tick
    TEST_ASSERT_EQUAL_UINT32(1, g.skipped());
    TEST_ASSERT_EQUAL(txgate::SKIP, g.update(true, 200));
    TEST_ASSERT_EQUAL_UINT32(2, g.skipped());
}

void test_busy_clears_and_the_next_tick_sends(void) {
    txgate::Gate g(500);
    g.update(false, 0);
    g.update(true, 100);                                      // one skip
    TEST_ASSERT_EQUAL(txgate::SEND, g.update(false, 200));    // ToA over -> sends
    TEST_ASSERT_EQUAL_UINT32(1, g.skipped());                 // count did not grow
}

void test_stuck_radio_is_forced_after_the_timeout(void) {
    // A missed TxDone leaves mode()==TX forever. The old code hung in waitPacketSent;
    // the gate bounds it: after stuck_ms of continuous busy, force idle and send.
    txgate::Gate g(500);
    g.update(false, 0);                                       // TX starts at t=0
    TEST_ASSERT_EQUAL(txgate::SKIP, g.update(true, 400));     // within bound: skip
    TEST_ASSERT_EQUAL(txgate::FORCE_IDLE_SEND, g.update(true, 501));
    TEST_ASSERT_EQUAL_UINT32(1, g.forced());
}

void test_force_rearms_the_stuck_clock(void) {
    txgate::Gate g(500);
    g.update(false, 0);
    g.update(true, 501);                                      // forced (counts 1)
    TEST_ASSERT_EQUAL(txgate::SKIP, g.update(true, 600));     // new TX, 99 ms busy: skip
    TEST_ASSERT_EQUAL(txgate::FORCE_IDLE_SEND, g.update(true, 1102));
    TEST_ASSERT_EQUAL_UINT32(2, g.forced());
}

void test_the_stuck_bound_is_TIME_not_ticks(void) {
    // Same 500 ms bound whether ticks arrive at 1 Hz or 10 Hz — constants in time, the
    // repo-wide rule, so the achieved TX rate degrades resolution rather than policy.
    txgate::Gate slow(500), fast(500);
    slow.update(false, 0);
    TEST_ASSERT_EQUAL(txgate::FORCE_IDLE_SEND, slow.update(true, 1000));  // 1 Hz tick
    fast.update(false, 0);
    for (unsigned long t = 100; t <= 400; t += 100)
        TEST_ASSERT_EQUAL(txgate::SKIP, fast.update(true, t));            // 10 Hz ticks
    TEST_ASSERT_EQUAL(txgate::FORCE_IDLE_SEND, fast.update(true, 500));   // bound is >=
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_idle_radio_sends_immediately);
    RUN_TEST(test_busy_radio_skips_and_counts);
    RUN_TEST(test_busy_clears_and_the_next_tick_sends);
    RUN_TEST(test_stuck_radio_is_forced_after_the_timeout);
    RUN_TEST(test_force_rearms_the_stuck_clock);
    RUN_TEST(test_the_stuck_bound_is_TIME_not_ticks);
    return UNITY_END();
}
