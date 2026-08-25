#include "packet.h"

#include <cstdio>

// Emit the ADR-0001 v1 packet: space-delimited KEY:VALUE ASCII tokens, leading
// V:1, in the canonical field order with the fixed unit suffixes (ft/C/V) and
// per-field precision (G/Pg/T one decimal, Batt two decimals).
size_t encode_packet(const Packet& p, char* out, size_t out_len) {
    if (out == nullptr || out_len == 0) {
        return 0;
    }

    int n = snprintf(
        out, out_len,
        "V:1 SYS:%u SRC:%u SEQ:%u St:%u ALT:%dft Max:%dft "
        "G:%.1f Pg:%.1f T:%.1fC Batt:%.2fV MET:%u "
        "Vel:%.1f Gmx:%.1f Gmn:%.1f",
        p.sys, p.src, p.seq, p.state,
        p.alt_ft, p.max_ft,
        static_cast<double>(p.g),
        static_cast<double>(p.pg),
        static_cast<double>(p.temp_c),
        static_cast<double>(p.batt_v),
        p.met_s,
        static_cast<double>(p.vel_fps),
        static_cast<double>(p.gmx),
        static_cast<double>(p.gmn));

    // TRUNCATION IS LOUD (both stages). The old contract returned out_len-1 — a
    // valid-looking length — and the fragment went to air, where it DECODED: a frame
    // cut at 105 B yielded a valid packet with MET:6 against a true 65535, no counter
    // moved (measured 2026-08-07, docs/newtag-collision-proof.md §5 context). No real
    // frame is 0 bytes, so 0 is the unambiguous failure return, and the buffer is
    // emptied so a caller that ignores the return value transmits nothing, not a lie.
    if (n < 0 || static_cast<size_t>(n) >= out_len) {
        out[0] = '\0';
        return 0;
    }

    // E+F tail, derived from St (A1.3): pad frames carry the raw 9-DoF channels —
    // the stationary calibration record — and flight frames carry the Wmx envelope
    // (instantaneous gyro at 10 Hz would alias; the window max survives any TX rate).
    int t;
    if (p.state == 0) {
        t = snprintf(out + n, out_len - n,
                     " Gyx:%.1f Gyy:%.1f Gyz:%.1f Mgx:%.1f Mgy:%.1f Mgz:%.1f",
                     static_cast<double>(p.gyx), static_cast<double>(p.gyy),
                     static_cast<double>(p.gyz), static_cast<double>(p.mgx),
                     static_cast<double>(p.mgy), static_cast<double>(p.mgz));
    } else {
        t = snprintf(out + n, out_len - n, " Wmx:%.1f", static_cast<double>(p.wmx));
    }
    if (t < 0 || static_cast<size_t>(t) >= out_len - n) {
        out[0] = '\0';
        return 0;
    }
    return static_cast<size_t>(n + t);
}
