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
        "G:%.1f Pg:%.1f T:%.1fC Batt:%.2fV MET:%u",
        p.sys, p.src, p.seq, p.state,
        p.alt_ft, p.max_ft,
        static_cast<double>(p.g),
        static_cast<double>(p.pg),
        static_cast<double>(p.temp_c),
        static_cast<double>(p.batt_v),
        p.met_s);

    if (n < 0) {
        out[0] = '\0';
        return 0;
    }
    // TRUNCATION IS LOUD. The old contract returned out_len-1 here — a valid-looking
    // length — and the fragment went to air, where it DECODED: a frame cut at 105 B
    // yielded a valid packet with MET:6 against a true 65535, no counter moved
    // (measured 2026-08-07, docs/newtag-collision-proof.md §5 context). No real frame
    // is 0 bytes, so 0 is the unambiguous failure return, and the buffer is emptied so
    // a caller that ignores the return value transmits nothing rather than a lie.
    if (static_cast<size_t>(n) >= out_len) {
        out[0] = '\0';
        return 0;
    }
    return static_cast<size_t>(n);
}
