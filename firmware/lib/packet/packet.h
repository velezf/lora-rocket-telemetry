#ifndef PACKET_H
#define PACKET_H

// Pure, portable C++ encoder for the ADR-0001 v1 telemetry packet.
// NO <Arduino.h>, NO RadioHead, NO Arduino String/types — builds and runs in
// PlatformIO's `native` host env. See docs/adr/0001-packet-format-v1.md.

#include <cstddef>

// Buffer size callers must give encode_packet(), and the single source of truth
// for it — main.cpp declares `char msg[PACKET_BUF_LEN]` rather than repeating a
// literal, so the buffer cannot drift away from what the encoder can emit.
//
// Measured worst case (all fields saturated, ADXL375 clipping at +/-200 g on
// every axis, and the additive Ax/Ay/Az tags present) is 143 bytes + NUL. The
// old `char msg[128]` predates the axis tags and is 15 bytes too small for that
// case: it would have TRUNCATED, not overflowed (encode_packet is bounded), but
// a truncated frame loses trailing tags. 160 leaves 16 bytes of headroom and is
// still far under RH_RF95_MAX_MESSAGE_LEN (251).
static const size_t PACKET_BUF_LEN = 160;

// Fields of a v1 packet. `V` is not stored: it is the constant 1 emitted first.
// Order of emission is fixed by the ADR field-spec table; these members mirror it.
struct Packet {
    unsigned int   sys;     // SYS  network id (0-255), default 7
    unsigned int   src;     // SRC  source vehicle (1=sled, 2=lander)
    unsigned int   seq;     // SEQ  per-TX counter, wraps at 65535
    unsigned int   state;   // St   flight state (0 pad / 1 ascent / 2 descent)
    int            alt_ft;  // ALT  barometric altitude, feet (may be negative)
    int            max_ft;  // Max  running max altitude, feet
    float          g;       // G    total accel magnitude, g (1 decimal)
    float          pg;      // Pg   peak G, g (1 decimal)
    float          temp_c;  // T    temperature, degC (1 decimal, may be negative)
    float          batt_v;  // Batt raw cell voltage, volts (2 decimals)
    unsigned int   met_s;   // MET  mission elapsed time, seconds

    // --- Additive v1 tags (ADR-0001 "additive tags within a version"): the
    // per-axis ADXL375 reading that `g` is the magnitude of. Emitted AFTER the
    // canonical 12 and only when `has_axes` is set, so a Packet that does not
    // opt in still encodes the ADR golden vector byte-for-byte. Ground decoders
    // surface these via the tolerated-unknown-tag path; no V bump.
    //
    // These carry default member initializers on purpose: existing call sites
    // declare `Packet p;` and assign fields one by one, so an uninitialized
    // `has_axes` would make emission depend on stack garbage.
    bool           has_axes = false;
    float          ax = 0.0f;   // Ax  body-axis accel, g (1 decimal, signed)
    float          ay = 0.0f;   // Ay
    float          az = 0.0f;   // Az
};

// Encode `p` into `out` (capacity `out_len`) as an ADR-0001 v1 packet string.
// Returns the number of bytes written, excluding the terminating NUL.
size_t encode_packet(const Packet& p, char* out, size_t out_len);

#endif // PACKET_H
