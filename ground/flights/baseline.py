"""v2 pad baseline — stability-gated trailing-window AGL zero.

Replaces the naive "rolling mean of every St:0 ALT" (which averages in stale early
pad drift and the boot-settling transient). Given a trailing sequence of pre-boost
pad ALT samples, drop the final pre-boost samples (handling / boost onset), take the
last `window` of what remains, and lock their mean as the baseline IFF that window is
quiet (stdev <= max_stdev). Unstable -> None, so the caller falls back to raw ALT.

Pure, stdlib only — the SAME function serves the live path (lock at flight_open) and
the derive path (recompute on rebuild). Parameters mirror the V1 firmware window
length adapted to the ~1 Hz ground packet rate; the variance gate is derived from
real F1 pad noise (V1 had none). See docs/agl-baseline-v2-audit.md.
"""
import statistics

WINDOW = 15        # trailing samples (~15 s at the ~1 Hz ground packet rate)
EXCLUDE_TAIL = 2   # drop the final ~2 s pre-boost (handling / boost onset)
MAX_STDEV = 2.0    # ft; quiet pad passes (F1: 0-1.6 ft), drift/motion fails (3.7 ft+)


def pad_baseline(samples, window=WINDOW, exclude_tail=EXCLUDE_TAIL, max_stdev=MAX_STDEV):
    """Return (baseline_ft, n_used) from a trailing run of pre-boost pad ALT samples.

    Drops the last `exclude_tail` samples, takes the last `window` of the remainder
    (skipping None), and returns their rounded mean if stdev <= max_stdev, else
    (None, 0). n_used is the number of samples actually averaged.
    """
    usable = samples[:-exclude_tail] if exclude_tail else list(samples)
    win = [a for a in usable[-window:] if a is not None]
    if not win:
        return None, 0
    sd = statistics.pstdev(win) if len(win) > 1 else 0.0
    if sd > max_stdev:
        return None, 0
    return round(statistics.fmean(win)), len(win)
