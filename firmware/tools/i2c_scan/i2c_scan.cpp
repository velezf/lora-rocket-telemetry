/*
 * ONE-SHOT I2C BUS CENSUS for the sled (Feather M0 + STEMMA QT chain).
 *
 * Build & flash:   pio run -e i2c_scan -t upload
 * Watch:           pio device monitor -e i2c_scan      (115200 baud)
 *
 * This exists as a COMMITTED, BUILDABLE artifact on purpose. Epic 5.1's
 * WHO_AM_I evidence came from a scratch sketch that no checkout can rebuild
 * (docs/epic5-integrity-note.md); the fix for that is not a better note, it is
 * an artifact with a git SHA. Record the SHA of the commit you flashed from
 * alongside the output and the result becomes citable.
 *
 * It does NOT touch main.cpp: `[env:i2c_scan]` builds only this file.
 *
 * WHAT IT ANSWERS IN ONE PASS — designed for a single round-trip:
 *   1. Which addresses ACK at all (three passes, so an intermittent device
 *      shows up as 1/3 or 2/3 rather than as a clean present/absent lie).
 *   2. For every address a known part could occupy, the IDENTITY REGISTER
 *      value — because an ACK only proves "something is there", and both
 *      0x1C/0x1E and 0x6A/0x6B and 0x76/0x77 are shared by several parts.
 *   3. Both bus speeds, because a marginal pull-up or a long QT chain can ACK
 *      at 100 kHz and fail at 400 kHz. That failure is otherwise discovered
 *      in flight.
 */
#include <Arduino.h>
#include <Wire.h>

static const uint8_t ADDR_LO = 0x08;
static const uint8_t ADDR_HI = 0x77;

// Identity registers, probed ONLY at addresses where that part can live, so the
// scan never pokes a register on a device it has not tentatively identified.
struct IdProbe {
    uint8_t addr;
    uint8_t reg;
    uint8_t expect;
    const char* part;
};

static const IdProbe ID_PROBES[] = {
    {0x1C, 0x0F, 0x3D, "LIS3MDL (SDO/SA1 low)"},
    {0x1E, 0x0F, 0x3D, "LIS3MDL (SDO/SA1 high)"},
    {0x1D, 0x00, 0xE5, "ADXL375/ADXL343 (ALT ADDRESS high)"},
    {0x53, 0x00, 0xE5, "ADXL375/ADXL343 (ALT ADDRESS low)"},
    {0x6A, 0x0F, 0x6C, "LSM6DSOX (SDO/SA0 low)"},
    {0x6B, 0x0F, 0x6C, "LSM6DSOX (SDO/SA0 high)"},
    {0x76, 0x00, 0x60, "BMP390 (SDO low)"},
    {0x77, 0x00, 0x60, "BMP390 (SDO high)"},
    {0x76, 0xD0, 0x61, "BME680 (SDO low)"},
    {0x77, 0xD0, 0x61, "BME680 (SDO high)"},
    {0x39, 0x92, 0xAB, "APDS9960"},
};
static const size_t N_ID_PROBES = sizeof(ID_PROBES) / sizeof(ID_PROBES[0]);

static bool ping(uint8_t addr) {
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

// Returns false if the register could not be read at all.
static bool read_reg(uint8_t addr, uint8_t reg, uint8_t* out) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;   // repeated start
    if (Wire.requestFrom(addr, (uint8_t)1) != 1) return false;
    *out = Wire.read();
    return true;
}

static void hex2(uint8_t v) {
    if (v < 0x10) Serial.print('0');
    Serial.print(v, HEX);
}

static void scan_at(uint32_t clk) {
    Wire.setClock(clk);
    Serial.print(F("\n--- BUS SCAN @ "));
    Serial.print(clk / 1000);
    Serial.println(F(" kHz, 3 passes ---"));

    uint8_t hits[0x78] = {0};
    for (uint8_t pass = 0; pass < 3; ++pass) {
        for (uint8_t a = ADDR_LO; a <= ADDR_HI; ++a) {
            if (ping(a)) hits[a]++;
        }
        delay(20);
    }

    uint8_t found = 0;
    for (uint8_t a = ADDR_LO; a <= ADDR_HI; ++a) {
        if (!hits[a]) continue;
        found++;
        Serial.print(F("ACK 0x"));
        hex2(a);
        Serial.print(F("  passes "));
        Serial.print(hits[a]);
        Serial.print(F("/3"));
        if (hits[a] != 3) Serial.print(F("   <<< INTERMITTENT"));

        bool identified = false;
        for (size_t i = 0; i < N_ID_PROBES; ++i) {
            if (ID_PROBES[i].addr != a) continue;
            uint8_t v = 0;
            if (!read_reg(a, ID_PROBES[i].reg, &v)) continue;
            Serial.print(F("\n      id reg 0x"));
            hex2(ID_PROBES[i].reg);
            Serial.print(F(" = 0x"));
            hex2(v);
            Serial.print(F("  expect 0x"));
            hex2(ID_PROBES[i].expect);
            Serial.print(F("  -> "));
            if (v == ID_PROBES[i].expect) {
                Serial.print(F("MATCH: "));
                Serial.print(ID_PROBES[i].part);
                identified = true;
            } else {
                Serial.print(F("no match for "));
                Serial.print(ID_PROBES[i].part);
            }
        }
        if (!identified) {
            Serial.print(F("\n      UNIDENTIFIED — see the decode table in docs/sensor-census.md"));
        }
        Serial.println();
    }
    Serial.print(F("total addresses ACKing: "));
    Serial.println(found);
}

void setup() {
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && (millis() - t0) < 8000) delay(10);

    Wire.begin();

    Serial.println(F("\n================================================"));
    Serial.println(F("APOGEE SLED I2C CENSUS"));
    Serial.print(F("built "));
    Serial.print(F(__DATE__));
    Serial.print(' ');
    Serial.println(F(__TIME__));
    Serial.println(F("RECORD THE GIT SHA YOU FLASHED FROM WITH THIS OUTPUT."));
    Serial.println(F("================================================"));

    scan_at(100000);
    scan_at(400000);

    Serial.println(F("\n--- END OF CENSUS. Copy everything above this line. ---"));
}

void loop() {
    delay(1000);
}
