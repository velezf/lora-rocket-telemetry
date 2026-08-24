#include <unity.h>
#include "envelope.h"

void setUp(void) {}
void tearDown(void) {}

// --- the core mechanism (ADR 0005 §4): an instantaneous sample at TX time misses a
// spike that lasted 20 ms; the envelope makes spike amplitudes exact at ANY TX rate ---

void test_a_spike_between_tx_ticks_survives_in_gmx(void) {
    envelope::Window w;
    w.note(1.0f);
    w.note(151.7f);          // 20 ms lateral hit, gone by the next TX tick
    w.note(1.0f);            // what an instantaneous read at TX time would see
    TEST_ASSERT_EQUAL_FLOAT(151.7f, w.gmx());
    TEST_ASSERT_EQUAL_FLOAT(1.0f, w.gmn());
}

void test_tracks_min_and_max_independently(void) {
    envelope::Window w;
    w.note(3.0f); w.note(0.1f); w.note(7.5f); w.note(2.0f);
    TEST_ASSERT_EQUAL_FLOAT(7.5f, w.gmx());
    TEST_ASSERT_EQUAL_FLOAT(0.1f, w.gmn());  // coast ~0 g is a real reading, not a failure
}

// --- reset per TX window: consumed values do not leak into the next frame ---

void test_reset_starts_a_fresh_window(void) {
    envelope::Window w;
    w.note(151.7f);
    w.reset();
    w.note(2.0f); w.note(3.0f);
    TEST_ASSERT_EQUAL_FLOAT(3.0f, w.gmx());  // the old spike is gone
    TEST_ASSERT_EQUAL_FLOAT(2.0f, w.gmn());
}

// --- an empty window (no samples since reset) reports the last known level, so a TX
// tick that outraces the sampler still sends a real number rather than a stale
// extreme or a fabricated zero ---

void test_empty_window_carries_the_last_level(void) {
    envelope::Window w;
    w.note(5.0f); w.note(1.2f);
    w.reset();                               // TX consumed the window; no sample since
    TEST_ASSERT_EQUAL_FLOAT(1.2f, w.gmx());  // last LEVEL, not the consumed max
    TEST_ASSERT_EQUAL_FLOAT(1.2f, w.gmn());
}

void test_before_any_sample_both_read_zero(void) {
    envelope::Window w;
    TEST_ASSERT_EQUAL_FLOAT(0.0f, w.gmx());
    TEST_ASSERT_EQUAL_FLOAT(0.0f, w.gmn());
}

// --- a skipped TX (no reset) EXTENDS the window instead of losing the samples: the
// envelope then honestly covers everything since the last frame that actually flew ---

void test_unreset_window_accumulates_across_a_tx_skip(void) {
    envelope::Window w;
    w.note(151.7f);          // window 1: spike
    // TX tick fires but the radio is still on air -> SKIP, no reset
    w.note(2.0f);            // window 2 samples
    TEST_ASSERT_EQUAL_FLOAT(151.7f, w.gmx());  // the spike still reaches the wire
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_a_spike_between_tx_ticks_survives_in_gmx);
    RUN_TEST(test_tracks_min_and_max_independently);
    RUN_TEST(test_reset_starts_a_fresh_window);
    RUN_TEST(test_empty_window_carries_the_last_level);
    RUN_TEST(test_before_any_sample_both_read_zero);
    RUN_TEST(test_unreset_window_accumulates_across_a_tx_skip);
    return UNITY_END();
}
