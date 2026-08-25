#ifndef TXGATE_H
#define TXGATE_H

// Non-blocking transmit gate (Phase 2 item 3) — pure and host-tested.
//
// WHY THIS EXISTS. The TX path was `rf95.send()` followed by `rf95.waitPacketSent()`,
// which spins until the frame is fully off the air. Sampling and transmitting share one
// thread, so every transmission stole sample ticks — measured at ~33 ms of every 59 ms
// sample period at 1 Hz TX, and at 10 Hz it would consume the loop outright. RadioHead's
// send() is already async-start (it returns once TX begins); the blocking was OUR
// explicit wait. Removing it needs a guard, because send() opens with its own
// waitPacketSent() (RH_RF95.cpp:334) — calling it while a frame is still on air blocks
// exactly like before. The guard is mode()==RHModeTx, polled, no SPI cost (the ISR
// maintains _mode).
//
// THE POLICY, decided and tested rather than implied:
//   SEND            — radio idle: transmit the CURRENT frame. There is no queue, by
//                     decision: frames are rebuilt fresh each tick, so a queued frame
//                     could only ever be staler than the one the next tick builds.
//   SKIP            — a send is due while the previous frame is still on air. Skip,
//                     count. THE CALLER MUST NOT INCREMENT SEQ on a skip — a sled
//                     scheduling decision must not be published as RF loss (SEQ gaps
//                     are the ground's loss statistic).
//   FORCE_IDLE_SEND — the radio has been continuously busy past stuck_ms: the TxDone
//                     interrupt was missed. This is the old unbounded-hang failure
//                     (waitPacketSent forever), relocated and BOUNDED: the caller
//                     forces setModeIdle(), and sends fresh. stuck_ms defaults to 500 —
//                     above any legitimate time-on-air in either bandwidth config
//                     (worst ASCII frame at BW125 is ~236 ms), far below the pad TX
//                     interval.
//
// SELF-ANCHORING, deliberately: the gate timestamps the TX start itself when it returns
// SEND / FORCE_IDLE_SEND (the caller transmits within the same tick). A "caller must
// report the start time" contract would be one forgotten call away from a stuck clock —
// the same class as a check that cannot fail, a contract that cannot be exercised.
//
// Constants are in TIME, not ticks — the repo-wide rule: the achieved TX rate degrades
// resolution, never policy.

namespace txgate {

enum Decision { SEND, SKIP, FORCE_IDLE_SEND };

class Gate {
public:
    explicit Gate(unsigned long stuck_ms = 500)
        : stuck_ms_(stuck_ms), tx_started_ms_(0), skipped_(0), forced_(0) {}

    // One TX tick: the radio's current busy state and the monotonic clock.
    Decision update(bool radio_busy, unsigned long now_ms) {
        if (!radio_busy) {
            tx_started_ms_ = now_ms;          // this tick transmits; anchor the clock
            return SEND;
        }
        if (now_ms - tx_started_ms_ >= stuck_ms_) {
            forced_++;
            tx_started_ms_ = now_ms;          // the forced send is a fresh TX
            return FORCE_IDLE_SEND;
        }
        skipped_++;
        return SKIP;
    }

    // Counters for the RATE line: skips are scheduling (not RF loss); forces are missed
    // TxDone interrupts — rare enough that any nonzero count deserves study.
    unsigned long skipped() const { return skipped_; }
    unsigned long forced()  const { return forced_; }

private:
    unsigned long stuck_ms_;
    unsigned long tx_started_ms_;
    unsigned long skipped_;
    unsigned long forced_;
};

}  // namespace txgate

#endif  // TXGATE_H
