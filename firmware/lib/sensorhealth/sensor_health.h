#ifndef SENSOR_HEALTH_H
#define SENSOR_HEALTH_H

// Per-sensor read isolation (Phase 2 item 4) — pure and host-tested.
//
// WHY THIS EXISTS. One sensor's I2C failure must never take out an unrelated
// responsibility: the pattern established at the baro read (a failed performReading()
// used to `return` from the whole loop, costing a transmission per bad read) is here
// extended to every sensor as a first-class seam. Each sensor's failures are counted
// SEPARATELY, so the RATE line can say WHICH bus peer is sick, and health is a
// per-sensor question the frame builder can ask ("omit the 9-DoF tags this frame" —
// missing tags are v1-legal; garbage values are not).
//
// HEALTH IS TIME SINCE LAST GOOD READ, not a count of consecutive failures. A count
// threshold means different things at 22 Hz and 1 Hz — the criterion-redefinition the
// repo's constants-in-time rule exists to prevent. Only SUCCESS refreshes the clock
// (the stuck-baro lesson: continuous failed attempts must not look like liveness), and
// a sensor never seen is UNHEALTHY, not vacuously fine — a health check that starts
// true before any evidence is a check that cannot fail.
//
// WHO IS COVERED. BARO only (BMP390: performReading() returns a real bool). The
// ADXL375, LSM6DSOX and LIS3MDL are ALL DELIBERATELY ABSENT — every one of their
// getEvent() paths returns true unconditionally over a void _read() (verified in the
// vendored sources: ADXL 2026-08, LSM6DS 4.7.4 + LIS3MDL 1.2.5 at 9-DoF integration
// 2026-08-25 — correcting this comment's earlier claim that those drivers report
// read success; they do not). Wiring health to an unconditional-true return would be
// a check that cannot fail. The obvious heuristic — zero magnitude means dead
// sensor — is FLIGHT-UNSAFE: a coasting rocket is ballistic and legitimately reads
// ~0 g (sentinel colliding with a legal value). IMU6/MAG are ENROLLED as of
// feat/i2c-hardening: src/main.cpp reads their data registers through
// Adafruit_I2CDevice, whose write_then_read returns real I2C status — a failed
// read updates nothing, is counted here, and sustained failure drops the tags
// from frames (in-flight degrade). Recorded here so nobody "fixes" the remaining
// ADXL gap with the zero-magnitude heuristic.

namespace sensors {

enum Id : unsigned char { BARO = 0, IMU6 = 1, MAG = 2, N_SENSORS = 3 };

class Health {
public:
    // stale_ms: how long without a successful read before a sensor is unhealthy.
    explicit Health(unsigned long stale_ms = 500) : stale_ms_(stale_ms) {
        for (unsigned char i = 0; i < N_SENSORS; i++) {
            failures_[i] = 0; consecutive_[i] = 0; last_ok_ms_[i] = 0; seen_ok_[i] = false;
        }
    }

    // Record one read attempt's outcome with its monotonic timestamp.
    void note(Id s, bool ok, unsigned long now_ms) {
        if (ok) {
            consecutive_[s] = 0;
            last_ok_ms_[s]  = now_ms;
            seen_ok_[s]     = true;
        } else {
            failures_[s]++;
            consecutive_[s]++;
        }
    }

    // Healthy == a successful read happened, recently. Failed attempts never refresh.
    bool healthy(Id s, unsigned long now_ms) const {
        if (!seen_ok_[s]) return false;
        return (now_ms - last_ok_ms_[s]) < stale_ms_;
    }

    unsigned long failures(Id s)    const { return failures_[s]; }
    unsigned long consecutive(Id s) const { return consecutive_[s]; }

private:
    unsigned long stale_ms_;
    unsigned long failures_[N_SENSORS];
    unsigned long consecutive_[N_SENSORS];
    unsigned long last_ok_ms_[N_SENSORS];
    bool          seen_ok_[N_SENSORS];
};

}  // namespace sensors

#endif  // SENSOR_HEALTH_H
