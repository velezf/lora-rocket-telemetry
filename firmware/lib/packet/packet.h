#ifndef PACKET_H
#define PACKET_H

// Pure, portable C++ encoder for the ADR-0001 v1 telemetry packet.
// NO <Arduino.h>, NO RadioHead, NO Arduino String/types — builds and runs in
// PlatformIO's `native` host env. See docs/adr/0001-packet-format-v1.md.

#include <cstddef>

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
};

// Encode `p` into `out` (capacity `out_len`) as an ADR-0001 v1 packet string.
// Returns the number of bytes written, excluding the terminating NUL.
size_t encode_packet(const Packet& p, char* out, size_t out_len);

#endif // PACKET_H
