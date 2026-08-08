"""v2 pad baseline — stability-gated trailing TIME-window AGL zero.

Replaces the naive "rolling mean of every St:0 ALT" (which averages in stale early
pad drift and the boot-settling transient). Given a trailing, time-ordered run of
pre-boost pad (t, ALT) samples, drop everything in the final `exclude_tail_s`
seconds (handling / boost onset), take the `window_s` seconds before that, and lock
their mean as the baseline IFF that window is quiet (stdev <= max_stdev). Unstable
-> None, so the caller falls back to raw ALT.

THE WINDOW IS WALL-CLOCK TIME, NOT A SAMPLE COUNT (ADR 0005 §7). The v1 constant
`WINDOW = 15` was a sample count calibrated in seconds at the ~1 Hz ground packet
rate; at 10 Hz it silently shrank the window to 1.5 s — quiet enough to pass the
variance gate while the rocket was still being handled. Time-based, the same 15 s
of pad data produces the same baseline at ANY packet rate.

`t` is the caller's monotonic clock in seconds (the segmenter's `t`, the
dashboard's `obs.mono`, derive's epoch seconds); only differences matter, and
samples must arrive time-ordered. At exactly 1 Hz these semantics reproduce the
old sample-count behaviour ("drop the last 2, average the previous 15").

Pure, stdlib only — the SAME function serves the live path (lock at flight_open)
and the derive path (recompute on rebuild). The variance gate is derived from real
F1 pad noise (V1 had none). See docs/agl-baseline-v2-audit.md.
"""
import statistics

WINDOW_S = 15.0        # seconds of trailing quiet pad averaged into the baseline
EXCLUDE_TAIL_S = 2.0   # final pre-boost seconds dropped (handling / boost onset)
MAX_STDEV = 2.0        # ft; quiet pad passes (F1: 0-1.6 ft), drift/motion fails (3.7 ft+)
HIST_KEEP_S = WINDOW_S + EXCLUDE_TAIL_S   # trailing history a caller must retain


def pad_baseline(samples, window_s=WINDOW_S, exclude_tail_s=EXCLUDE_TAIL_S,
                 max_stdev=MAX_STDEV):
    """Return (baseline_ft, n_used) from time-ordered (t_seconds, alt_ft) pairs.

    Anchored at the newest sample's t: drops samples newer than
    `t - exclude_tail_s`, averages those within the `window_s` seconds before
    that cut (skipping None altitudes), and returns the rounded mean if their
    stdev <= max_stdev, else (None, 0). n_used is the number of samples actually
    averaged — a sample count, so it scales with the packet rate.
    """
    if not samples:
        return None, 0
    cut = samples[-1][0] - exclude_tail_s
    lo = cut - window_s
    win = [a for t, a in samples if lo < t <= cut and a is not None]
    if not win:
        return None, 0
    sd = statistics.pstdev(win) if len(win) > 1 else 0.0
    if sd > max_stdev:
        return None, 0
    return round(statistics.fmean(win)), len(win)


def trim_history(samples):
    """The trailing slice of (t, alt) history still usable by a future
    `pad_baseline` call: everything within `HIST_KEEP_S` of the newest sample.
    Time-based, so the retained history is one window's worth at ANY packet
    rate — the count-based `WINDOW + EXCLUDE_TAIL` bound held 1.7 s at 10 Hz.
    Returns a list; callers keep their own container type."""
    if not samples:
        return []
    cutoff = samples[-1][0] - HIST_KEEP_S
    return [s for s in samples if s[0] > cutoff]
