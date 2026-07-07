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
    // On truncation snprintf returns the would-be length; report bytes actually
    // written (never counting the NUL, never past the buffer).
    if (static_cast<size_t>(n) >= out_len) {
        return out_len - 1;
    }
    return static_cast<size_t>(n);
}
