#ifndef TXSCHED_H
#define TXSCHED_H

// St-dependent TX schedule (ADR 0005, build-order step 7) — pure and host-tested.
//
// THE POLICY: 1 Hz on the pad, 10 Hz in flight — and the fast window is BOUNDED BY
// MET, because nothing else bounds it: the flight states latch and there is no St:3
// ("landed"), so "fast while St != 0" would key the PA at 58.9 % duty until the
// battery died in the recovery grass. MET is the only exit, anchored to launch_ms()
// (backdated to the accel gate, i.e. true MET zero — not to when anyone first asks).
//
// STATELESS, deliberately. A stateful "start the window now" implementation is one
// re-anchor away from the unbounded-latch class the launch-confirm work removed
// (an oscillating input re-opening PROVISIONAL forever). A pure function of
// (in_flight, now, launch) has no anchor to move; the contract is pinned by
// test_window_measured_from_launch_not_first_query either way.
//
// FAST_WINDOW_MS = 300 s — CHOSEN, NOT MEASURED, and sized like confirm_ms was
// (generous, on asymmetric risk): worst realistic flight this system flies is
// ~145 s (L2 to ~2500 ft boost+coast ~20 s, chute descent at ~20 ft/s ~125 s), so
// 300 s is ~2x that. Too SHORT truncates the descent record at 10 Hz — flight data
// lost, unrecoverable. Too LONG only spends battery: ~3000 extra frames at 17 dBm,
// minutes of margin, and the sled still beacons at 1 Hz for recovery afterwards.
// Interaction noted: FLIGHT_TX_MS (100 ms) is BELOW txgate's stuck_ms (500 ms), so
// a wedged radio in flight costs up to 4 SKIPs before FORCE_IDLE_SEND — bounded,
// and SEQ does not advance on those skips.
//
// Constants are in TIME (the repo-wide rule) and live HERE only; main.cpp cites
// this header rather than restating numbers.

namespace txsched {

constexpr unsigned long PAD_TX_MS      = 1000;    // 1 Hz  — St:0 / pad, and post-window
constexpr unsigned long FLIGHT_TX_MS   = 100;     // 10 Hz — the ADR 0005 decision
constexpr unsigned long FAST_WINDOW_MS = 300000;  // 300 s from MET zero (see above)

// The TX interval to honour right now. `launch_ms` is meaningful only when
// `in_flight` is true (launch::Confirm::launch_ms(), backdated to the accel gate).
//
// The delta is computed at EXPLICIT 32-bit width: millis() is uint32_t, and the
// usual `now - then` idiom only survives its wrap when the subtraction is done at
// the same width. On the M0 `unsigned long` IS 32-bit so plain subtraction works;
// on the 64-bit HOST it is not, and the wrap test fails — i.e. the two builds
// would disagree. uint32_t makes host behaviour equal target behaviour.
inline unsigned long interval_ms(bool in_flight, unsigned long now_ms,
                                 unsigned long launch_ms) {
    if (!in_flight) return PAD_TX_MS;
    const unsigned long met_ms =
        (unsigned long)((now_ms - launch_ms) & 0xFFFFFFFFUL);
    return (met_ms < FAST_WINDOW_MS) ? FLIGHT_TX_MS : PAD_TX_MS;
}

}  // namespace txsched

#endif  // TXSCHED_H
