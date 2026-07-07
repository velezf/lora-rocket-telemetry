#ifndef CONVERT_H
#define CONVERT_H

// Pure, portable unit conversions for the telemetry pipeline.
// No <Arduino.h>, no RadioHead — compiles and runs in the native host env.

// Total acceleration magnitude in g, given components in m/s^2.
// magnitude = sqrt(ax^2 + ay^2 + az^2) / 9.80665
float accel_magnitude_g(float ax, float ay, float az);

// Barometric altitude in feet relative to ground pressure.
// altitude_m = 44330 * (1 - (pressure/ground)^(1/5.255)); returns altitude_m * 3.28084.
// Both pressures in the same units (e.g. hPa).
float pressure_to_altitude_ft(float pressure_hPa, float ground_hPa);

#endif  // CONVERT_H
