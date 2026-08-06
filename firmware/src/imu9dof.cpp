#include "imu9dof.h"

#if defined(ARDUINO)

namespace imu9dof {

bool Sled9Dof::begin(TwoWire* wire) {
    have_gyro_ = false;
    have_mag_ = false;
    gyro_addr_ = 0;
    mag_addr_ = 0;

    for (uint8_t i = 0; i < 2 && !have_gyro_; ++i) {
        if (lsm_.begin_I2C(LSM6DSOX_ADDRS[i], wire)) {
            have_gyro_ = true;
            gyro_addr_ = LSM6DSOX_ADDRS[i];
        }
    }
    for (uint8_t i = 0; i < 2 && !have_mag_; ++i) {
        if (lis_.begin_I2C(LIS3MDL_ADDRS[i], wire)) {
            have_mag_ = true;
            mag_addr_ = LIS3MDL_ADDRS[i];
        }
    }

    if (have_gyro_) {
        // Widest gyro range: a rocket roll can run to hundreds of dps and a
        // saturated gyro is unrecoverable after the fact. 2000 dps matches
        // imu::gyro_mdps_per_lsb(GYRO_RANGE_DPS).
        lsm_.setGyroRange(LSM6DS_GYRO_RANGE_2000_DPS);
        // The LSM6DSOX accelerometer is NOT the launch-detect channel — it
        // tops out at 16 g and a boost saturates it. ADXL375 (+/-200 g) keeps
        // that job. This axis set exists for attitude, not for peak-g.
        lsm_.setAccelRange(LSM6DS_ACCEL_RANGE_16_G);
        // Sensor ODR must EXCEED the loop's 20 Hz sample tick, or successive
        // reads return the same conversion and the "20 Hz" record is a lie.
        lsm_.setGyroDataRate(LSM6DS_RATE_208_HZ);
        lsm_.setAccelDataRate(LSM6DS_RATE_208_HZ);
    }
    if (have_mag_) {
        lis_.setRange(LIS3MDL_RANGE_4_GAUSS);   // matches imu::mag_lsb_per_gauss
        lis_.setPerformanceMode(LIS3MDL_MEDIUMMODE);
        lis_.setOperationMode(LIS3MDL_CONTINUOUSMODE);
        lis_.setDataRate(LIS3MDL_DATARATE_155_HZ);
    }

    return have_gyro_ && have_mag_;
}

Reading Sled9Dof::read() {
    Reading r;
    r.gx_raw = r.gy_raw = r.gz_raw = 0;
    r.mx_raw = r.my_raw = r.mz_raw = 0;
    r.gx_dps = r.gy_dps = r.gz_dps = 0.0f;
    r.mx_ut = r.my_ut = r.mz_ut = 0.0f;
    r.gyro_saturated = false;
    r.mag_saturated = false;
    r.ok = have_gyro_ && have_mag_;
    if (!r.ok) {
        return r;
    }

    const float g_scale = imu::gyro_mdps_per_lsb(GYRO_RANGE_DPS);
    const float m_scale = imu::mag_lsb_per_gauss(MAG_RANGE_GAUSS);

    // One 14-byte burst (temp + gyro + accel) — the Adafruit driver's own read.
    sensors_event_t a, g, t;
    lsm_.getEvent(&a, &g, &t);
    r.gx_raw = lsm_.rawGyroX;
    r.gy_raw = lsm_.rawGyroY;
    r.gz_raw = lsm_.rawGyroZ;

    // One 6-byte burst.
    lis_.read();
    r.mx_raw = lis_.x;
    r.my_raw = lis_.y;
    r.mz_raw = lis_.z;

    r.gx_dps = imu::gyro_dps(r.gx_raw, g_scale);
    r.gy_dps = imu::gyro_dps(r.gy_raw, g_scale);
    r.gz_dps = imu::gyro_dps(r.gz_raw, g_scale);
    r.mx_ut  = imu::mag_ut(r.mx_raw, m_scale);
    r.my_ut  = imu::mag_ut(r.my_raw, m_scale);
    r.mz_ut  = imu::mag_ut(r.mz_raw, m_scale);

    r.gyro_saturated = imu::is_saturated(r.gx_raw) ||
                       imu::is_saturated(r.gy_raw) ||
                       imu::is_saturated(r.gz_raw);
    r.mag_saturated  = imu::is_saturated(r.mx_raw) ||
                       imu::is_saturated(r.my_raw) ||
                       imu::is_saturated(r.mz_raw);
    return r;
}

}  // namespace imu9dof

#endif  // ARDUINO
