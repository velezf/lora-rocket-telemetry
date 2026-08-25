#ifndef ENVELOPE_H
#define ENVELOPE_H

// G envelope across a TX window — `Gmx`/`Gmn` (ADR 0005 §4, promoting increment 2's
// peak-hold from a nicety to the core mechanism).
//
// WHY AN ENVELOPE AND NOT A SAMPLE. An instantaneous read at TX time misses the peak of
// a spike that lasted 20 ms, and the plotted amplitude would then depend on sampling
// phase. Tracking min/max of |a| across the window makes spike amplitudes exact at ANY
// TX rate — the plot's correctness is decoupled from the rate decision entirely.
//
// RESET DISCIPLINE (the part main.cpp must honour): reset() is called ONLY when a frame
// carrying the values actually goes to air. On a TX SKIP (radio still on air) or an
// encode drop, the window is NOT reset — it extends, so the envelope honestly covers
// everything since the last frame that flew and no spike is ever lost to scheduling.
//
// Pure, portable C++ — no <Arduino.h> (lib/ purity rule).

namespace envelope {

class Window {
public:
    Window() : gmx_(0.0f), gmn_(0.0f), last_(0.0f), empty_(true), seen_any_(false) {}

    // Feed one |accel| magnitude, g. ~0 g on a coasting rocket is a real reading —
    // the min tracks it like any other value (zero is NOT a failure sentinel here).
    void note(float g) {
        if (empty_) {
            gmx_ = gmn_ = g;
            empty_ = false;
        } else {
            if (g > gmx_) gmx_ = g;
            if (g < gmn_) gmn_ = g;
        }
        last_ = g;
        seen_any_ = true;
    }

    // Window extremes. An EMPTY window (no note since reset) reports the last known
    // level for both — a real number, not the consumed extreme and not a fabricated 0.
    // Before any sample at all, both read 0.
    float gmx() const { return empty_ ? (seen_any_ ? last_ : 0.0f) : gmx_; }
    float gmn() const { return empty_ ? (seen_any_ ? last_ : 0.0f) : gmn_; }

    // Start a fresh window. Call ONLY when a frame actually went to air (see reset
    // discipline above) — whether or not that frame's SHAPE carried this window's
    // tag: a pad frame resets the gyro window it did not transmit, discarding
    // stationary-pad samples a max cannot be raised by. What must never happen is a
    // reset on a frame that did NOT fly (SKIP / encode drop).
    void reset() { empty_ = true; }

private:
    float gmx_, gmn_;
    float last_;       // most recent magnitude, for the empty-window carry
    bool  empty_;      // no note since the last reset
    bool  seen_any_;   // any note ever (distinguishes carry from cold start)
};

}  // namespace envelope

#endif  // ENVELOPE_H
