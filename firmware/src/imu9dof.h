#ifndef IMU9DOF_H
#define IMU9DOF_H

// I2C TRANSPORT GLUE for the sled's 9-DoF pair (LSM6DSOX gyro/accel + LIS3MDL
// magnetometer). Hardware-only: Wire, Adafruit drivers, address probing,
// WHO_AM_I verification. All arithmetic lives in `firmware/lib/imu/imu.h`,
// which is host-tested in the `native` env — nothing here does maths.
//
// Guarded on ARDUINO so the file is inert if the native env is ever told to
// build src/ (it is not today: `test_build_src` defaults to off).
//
// STATUS: NOT WIRED INTO THE FLIGHT LOOP. `firmware/src/main.cpp` is owned by
// another stream and is not edited here. The exact proposed integration is
// `docs/patches/0001-main-cpp-9dof.patch`, unapplied by design.

#if defined(ARDUINO)

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_LSM6DSOX.h>
#include <Adafruit_LIS3MDL.h>

#include <imu.h>

namespace imu9dof {

// Both parts expose an address-select pin, so both have TWO valid addresses.
// The firmware PROBES rather than hardcodes: a hardcoded address turns a
// jumper change or a different breakout revision into "sensor not found",
// and — worse — a WHO_AM_I check against a hardcoded address cannot tell
// "absent" from "present at the other address".
//
// LSM6DSOX: SDO/SA0 low -> 0x6A (Adafruit breakout default), high -> 0x6B.
// LIS3MDL:  SDO/SA1 low -> 0x1C (Adafruit breakout default), high -> 0x1E.
static const uint8_t LSM6DSOX_ADDRS[2] = {0x6A, 0x6B};
static const uint8_t LIS3MDL_ADDRS[2]  = {0x1C, 0x1E};

// Configured full scales. These are the numbers the pure sensitivity tables are
// keyed on; changing one here without changing the other silently rescales
// every reading, which is why both sides are constants and not literals.
static const int GYRO_RANGE_DPS   = 2000;
static const int MAG_RANGE_GAUSS  = 4;

struct Reading {
    // Raw counts, kept so saturation is testable on the count (see imu.h).
    int16_t gx_raw, gy_raw, gz_raw;
    int16_t mx_raw, my_raw, mz_raw;
    // Engineering units, via the pure layer.
    float gx_dps, gy_dps, gz_dps;
    float mx_ut,  my_ut,  mz_ut;
    bool  gyro_saturated;
    bool  mag_saturated;
    bool  ok;
};

class Sled9Dof {
  public:
    Sled9Dof() : gyro_addr_(0), mag_addr_(0), have_gyro_(false), have_mag_(false) {}

    // Probes both candidate addresses for each part. The Adafruit `begin_I2C`
    // verifies WHO_AM_I internally (LSM6DSOX chip id 0x6C, LIS3MDL 0x3D) and
    // returns false on mismatch, so a foreign device answering at the same
    // address is rejected rather than driven.
    // Returns true only if BOTH parts were found and configured.
    bool begin(TwoWire* wire = &Wire);

    // Single burst read of each part; no conversion happens in the driver.
    Reading read();

    // 0 when the part was not found. Report these, don't assume them.
    uint8_t gyro_address() const { return gyro_addr_; }
    uint8_t mag_address() const { return mag_addr_; }
    bool have_gyro() const { return have_gyro_; }
    bool have_mag() const { return have_mag_; }

  private:
    Adafruit_LSM6DSOX lsm_;
    Adafruit_LIS3MDL  lis_;
    uint8_t gyro_addr_;
    uint8_t mag_addr_;
    bool have_gyro_;
    bool have_mag_;
};

}  // namespace imu9dof

#endif  // ARDUINO
#endif  // IMU9DOF_H
