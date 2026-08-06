#include "imu.h"

#include <cmath>

namespace imu {

float gyro_mdps_per_lsb(int range_dps) {
    switch (range_dps) {
        case 125:  return 4.375f;
        case 250:  return 8.75f;
        case 500:  return 17.50f;
        case 1000: return 35.0f;
        case 2000: return 70.0f;
        default:   return 0.0f;   // refusal, not a guess
    }
}

float mag_lsb_per_gauss(int range_gauss) {
    switch (range_gauss) {
        case 4:  return 6842.0f;
        case 8:  return 3421.0f;
        case 12: return 2281.0f;
        case 16: return 1711.0f;
        default: return 0.0f;     // refusal, not a guess
    }
}

float gyro_dps(int raw, float mdps_per_lsb) {
    return static_cast<float>(raw) * mdps_per_lsb / 1000.0f;
}

float mag_ut(int raw, float lsb_per_gauss) {
    if (lsb_per_gauss == 0.0f) {
        return 0.0f;
    }
    // gauss -> microtesla is exactly x100.
    return (static_cast<float>(raw) / lsb_per_gauss) * 100.0f;
}

bool is_saturated(int raw) {
    return raw >= 32767 || raw <= -32768;
}

static float pick(float x, float y, float z, Axis a) {
    switch (a) {
        case Axis::X: return x;
        case Axis::Y: return y;
        default:      return z;
    }
}

float roll_rate_dps(float gx, float gy, float gz, Axis longitudinal) {
    return pick(gx, gy, gz, longitudinal);
}

float tilt_off_axis_deg(float ax, float ay, float az, Axis longitudinal) {
    const float mag = std::sqrt(ax * ax + ay * ay + az * az);
    if (!(mag > 0.0f)) {
        return -1.0f;   // no direction to report
    }
    // |axial| folds nose-up and nose-down onto the same angle off the axis.
    float c = std::fabs(pick(ax, ay, az, longitudinal)) / mag;
    if (c > 1.0f) c = 1.0f;   // guard acos against float rounding past 1
    return std::acos(c) * 57.2957795130823f;   // 180/pi
}

void BiasAccumulator::add(float x, float y, float z) {
    sx_ += x;
    sy_ += y;
    sz_ += z;
    ++n_;
}

bool BiasAccumulator::add_if_still(float x, float y, float z, float gate) {
    if (std::fabs(x) > gate || std::fabs(y) > gate || std::fabs(z) > gate) {
        return false;
    }
    add(x, y, z);
    return true;
}

float BiasAccumulator::mean_x() const { return n_ ? sx_ / static_cast<float>(n_) : 0.0f; }
float BiasAccumulator::mean_y() const { return n_ ? sy_ / static_cast<float>(n_) : 0.0f; }
float BiasAccumulator::mean_z() const { return n_ ? sz_ / static_cast<float>(n_) : 0.0f; }

void BiasAccumulator::reset() {
    sx_ = sy_ = sz_ = 0.0f;
    n_ = 0;
}

}  // namespace imu
