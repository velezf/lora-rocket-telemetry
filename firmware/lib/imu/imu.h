#ifndef IMU_H
#define IMU_H

// Pure, portable 9-DoF conversions and derivations for the LSM6DSOX gyro and
// the LIS3MDL magnetometer.
//
// NO <Arduino.h>, NO Wire.h, NO Adafruit driver headers — this compiles and runs
// in PlatformIO's `native` host env (`pio test -e native`). Everything here is
// arithmetic over numbers that a transport handed us. The I2C transport, the
// address probe and the WHO_AM_I check live in `firmware/src/imu9dof.*`.
//
// Why the split is worth it here specifically: every failure this layer can have
// is SILENT in the data. A wrong sensitivity constant produces a plausible roll
// rate; an unfolded tilt angle produces a plausible attitude; a bias averaged
// over a bumped pad produces a plausible zero. None of them raise an error and
// none are visible in a flight record after the fact — so they have to be pinned
// by tests on the ground, where they can still fail.

namespace imu {

// Which board axis lies along the vehicle's long (roll) axis, as mounted.
// This is a MOUNTING fact, not a sensor fact — it changes when the sled is
// re-oriented in the airframe, and nothing in the data reveals a wrong choice.
enum class Axis { X = 0, Y = 1, Z = 2 };

// LSM6DSOX angular-rate sensitivity in milli-dps per LSB, by full-scale range
// in dps (datasheet Table 2, "Mechanical characteristics", So_G).
// Returns 0.0f for an unsupported range — callers MUST treat 0 as a refusal.
float gyro_mdps_per_lsb(int range_dps);

// LIS3MDL magnetic sensitivity in LSB per gauss, by full-scale range in gauss
// (datasheet Table 3). Returns 0.0f for an unsupported range.
float mag_lsb_per_gauss(int range_gauss);

// Raw signed 16-bit gyro count -> degrees per second.
float gyro_dps(int raw, float mdps_per_lsb);

// Raw signed 16-bit magnetometer count -> microtesla (1 gauss = 100 uT).
float mag_ut(int raw, float lsb_per_gauss);

// True when a raw count sits on either 16-bit rail, i.e. the physical quantity
// exceeded the configured full scale and the value is a floor/ceiling, not a
// measurement. Must be tested on the COUNT: at 2000 dps the full-scale count
// converts to ~2293 dps, so a range check on the converted value misses it.
bool is_saturated(int raw);

// Angular rate about the vehicle's long axis, deg/s, signed.
float roll_rate_dps(float gx, float gy, float gz, Axis longitudinal);

// Angle between the measured acceleration vector and the vehicle's long axis,
// in degrees, FOLDED to 0..90 so that nose-up and nose-down both read 0.
// Standing still on the pad this is the angle off vertical.
// Returns -1.0f when the vector has no direction (free fall, or a dead read) —
// an explicit sentinel, never 0, because 0 means "perfectly vertical" and that
// is the worst possible thing to assert when nothing is known.
float tilt_off_axis_deg(float ax, float ay, float az, Axis longitudinal);

// Zero-rate-offset accumulator: the calibration primitive. A MEMS gyro reads
// non-zero at rest, and that offset integrates into attitude error, so it is
// measured on the pad and subtracted. `add_if_still` refuses samples above a
// motion gate, because a bias averaged over movement silently absorbs the
// movement.
class BiasAccumulator {
  public:
    BiasAccumulator() : sx_(0.0f), sy_(0.0f), sz_(0.0f), n_(0) {}

    void add(float x, float y, float z);

    // Folds the sample in only if every component is within `gate` of zero.
    // Returns true if it was accepted.
    bool add_if_still(float x, float y, float z, float gate);

    int count() const { return n_; }
    bool ready(int n_required) const { return n_ >= n_required; }

    float mean_x() const;
    float mean_y() const;
    float mean_z() const;

    void reset();

  private:
    float sx_, sy_, sz_;
    int n_;
};

}  // namespace imu

#endif  // IMU_H
