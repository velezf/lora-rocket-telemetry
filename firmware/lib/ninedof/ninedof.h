#ifndef NINEDOF_H
#define NINEDOF_H

// Raw->unit conversions for the 9-DoF raw-read path (feat/i2c-hardening).
//
// WHY RAW READS EXIST. The vendored LSM6DS/LIS3MDL getEvent() paths return true
// unconditionally and DISCARD the underlying I2C status — on a failed read they
// parse an uninitialized buffer (RESUME's named hazard: a dead sensor in flight
// freezes or FABRICATES spin data with no wire evidence). src/main.cpp therefore
// reads the data registers itself through Adafruit_I2CDevice, which reports real
// I2C success, enabling sensors::Health enrollment and in-flight degrade.
//
// EQUIVALENCE, STATED HONESTLY (red team F1 falsified the original "bit-identical"
// claim): the MAG conversion is exhaustively identical to the vendored pipeline at
// wire precision (0/65536 raws differ at %.1f). The GYRO conversion is NUMERICALLY
// equivalent (max deviation ~2e-4 dps, bounded by test) but NOT format-identical:
// the old path double-rounded through a float rad/s intermediate, and ~2.9 % of
// raw values (1,884/65,536) land 0.1 dps away at %.1f. The direct value here is
// the more correct one; a bench trace from a pre-swap build may legitimately
// differ by 0.1 in Gy?/Wmx — that is this change, not a defect.
//
// Pure, portable C++ — no <Arduino.h>, no BusIO (lib/ purity rule).

#include <cstdint>

namespace ninedof {

// LSM6DSOX gyro at ±2000 dps FS: 70 mdps/LSB. A1.4's ±2293.8 figure is the
// negative int16 extreme (-32768 × 0.07).
inline float gyro_raw_to_dps(int16_t raw) {
    return raw * 0.070f;
}

// LIS3MDL at ±4 gauss FS: 6842 LSB/gauss; 1 gauss = 100 µT. A1.4's ±478.9 is
// the int16 extreme through this factor.
inline float mag_raw_to_ut(int16_t raw) {
    return raw * (100.0f / 6842.0f);
}

// Both chips emit little-endian X_L X_H pairs; the sign path is the one a
// byte-order mistake corrupts silently.
inline int16_t le16(const unsigned char *b) {
    return static_cast<int16_t>(static_cast<uint16_t>(b[0]) |
                                (static_cast<uint16_t>(b[1]) << 8));
}

}  // namespace ninedof

#endif  // NINEDOF_H
