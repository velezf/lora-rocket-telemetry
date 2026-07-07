"""Per-(SYS,SRC) link-quality and packet-loss statistics (Epic 4.3).

Pure Python, stdlib only — no radio/file/I-O imports. Host-testable, runs
identically on Mac and Pi (`python3 -m unittest`), same discipline as
ground/decode.

Design decision D3: stats are tracked PER (sys, src) key, never a global
last_seq. Each transmitter (identified by its SYS+SRC pair) owns an independent
sequence counter, so a gap on one source must never be attributed to another.

SEQ is a uint16 that wraps at 65535 (ADR 0001, packet-format-v1). Missed-packet
inference is therefore modulo 65536:

    missed = (seq - last_seq - 1) mod 65536

Examples: last=65535,seq=0 -> 0 missed; last=65535,seq=2 -> 2 missed;
last=5,seq=8 -> 2 missed. The first packet for a key seeds last_seq with 0 gap.
"""
from __future__ import annotations

_SEQ_MOD = 65536  # uint16 wrap (SEQ wraps at 65535)


class _Key:
    """Mutable running stats for one (sys, src) transmitter."""

    __slots__ = (
        "last_seq",
        "rx_count",
        "gap_count",
        "rssi_min",
        "rssi_max",
        "_rssi_sum",
        "_rssi_n",
    )

    def __init__(self, seq: int) -> None:
        self.last_seq = seq
        self.rx_count = 0
        self.gap_count = 0
        self.rssi_min = None
        self.rssi_max = None
        self._rssi_sum = 0.0
        self._rssi_n = 0

    def record_rssi(self, rssi) -> None:
        if rssi is None:
            return
        if self.rssi_min is None or rssi < self.rssi_min:
            self.rssi_min = rssi
        if self.rssi_max is None or rssi > self.rssi_max:
            self.rssi_max = rssi
        self._rssi_sum += rssi
        self._rssi_n += 1

    @property
    def rssi_mean(self):
        if self._rssi_n == 0:
            return None
        return self._rssi_sum / self._rssi_n


class LinkStats:
    """Tracks packet-loss and link quality per (sys, src) key.

    Never keeps a global last_seq — each (sys, src) has its own counter.
    """

    def __init__(self) -> None:
        self._keys = {}

    def update(self, sys: int, src: int, seq: int, rssi=None) -> None:
        """Record one received packet for transmitter (sys, src).

        Infers missed packets from the SEQ delta (uint16 wraparound aware) and
        folds the RSSI reading into the running min/max/mean. RSSI may be None
        (unknown), in which case it is counted as received but excluded from the
        RSSI stats.
        """
        key = (sys, src)
        k = self._keys.get(key)
        if k is None:
            # First packet for this transmitter: seed, no gap inferred.
            k = _Key(seq)
            self._keys[key] = k
            k.rx_count = 1
            k.record_rssi(rssi)
            return

        # Missed packets since the last SEQ (modulo uint16 wrap).
        missed = (seq - k.last_seq - 1) % _SEQ_MOD
        k.gap_count += missed
        k.last_seq = seq
        k.rx_count += 1
        k.record_rssi(rssi)

    def snapshot(self) -> dict:
        """Return per-(sys,src) stats as a plain dict.

        {(sys, src): {"rx", "gaps", "last_seq",
                      "rssi_min", "rssi_max", "rssi_mean"}}
        """
        out = {}
        for key, k in self._keys.items():
            out[key] = {
                "rx": k.rx_count,
                "gaps": k.gap_count,
                "last_seq": k.last_seq,
                "rssi_min": k.rssi_min,
                "rssi_max": k.rssi_max,
                "rssi_mean": k.rssi_mean,
            }
        return out
