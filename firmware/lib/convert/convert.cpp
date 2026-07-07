#include "convert.h"

#include <cmath>

static const float kStandardGravity = 9.80665f;  // m/s^2
static const float kMetersToFeet = 3.28084f;

float accel_magnitude_g(float ax, float ay, float az) {
    return std::sqrt(ax * ax + ay * ay + az * az) / kStandardGravity;
}

float pressure_to_altitude_ft(float pressure_hPa, float ground_hPa) {
    float altitude_m =
        44330.0f * (1.0f - std::pow(pressure_hPa / ground_hPa, 1.0f / 5.255f));
    return altitude_m * kMetersToFeet;
}
