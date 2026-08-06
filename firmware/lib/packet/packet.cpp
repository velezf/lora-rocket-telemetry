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

    // Additive v1 tags appended after the canonical 12 (ADR-0001 allows new tags
    // within a version; receivers tolerate and surface what they don't know).
    // Skipped entirely when absent, which keeps the golden vector byte-exact.
    if (p.has_axes) {
        size_t used = static_cast<size_t>(n);
        int m = snprintf(
            out + used, out_len - used,
            " Ax:%.1f Ay:%.1f Az:%.1f",
            static_cast<double>(p.ax),
            static_cast<double>(p.ay),
            static_cast<double>(p.az));
        if (m < 0) {
            return used;                       // leave the v1 prefix intact
        }
        if (static_cast<size_t>(m) >= out_len - used) {
            return out_len - 1;                // truncated at the buffer edge
        }
        n += m;
    }

    return static_cast<size_t>(n);
}
