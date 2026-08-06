#include <unity.h>
#include <cstring>
#include "packet.h"

void setUp(void) {}
void tearDown(void) {}

// Golden vector from docs/adr/0001-packet-format-v1.md (single source of truth).
static const char *GOLDEN =
    "V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft "
    "G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12";

// The golden input corresponding to GOLDEN above.
static Packet golden_input(void) {
    Packet p;
    p.sys = 7;
    p.src = 1;
    p.seq = 42;
    p.state = 1;
    p.alt_ft = 1234;
    p.max_ft = 5678;
    p.g = 2.3f;
    p.pg = 9.1f;
    p.temp_c = 21.5f;
    p.batt_v = 3.92f;
    p.met_s = 12;
    return p;
}

// The encoder reproduces the ADR golden vector byte-for-byte.
void test_encodes_golden_vector(void) {
    Packet p = golden_input();
    char buf[128];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(GOLDEN, buf);
    TEST_ASSERT_EQUAL_size_t(strlen(GOLDEN), n);
}

// Second fixture: guards field order, negatives, wraps, and rounding
// (G/Pg/T one decimal, Batt two decimals).
void test_encodes_second_fixture(void) {
    Packet p;
    p.sys = 255;
    p.src = 2;
    p.seq = 65535;
    p.state = 0;
    p.alt_ft = -123;
    p.max_ft = 20000;
    p.g = 0.94f;      // -> 0.9
    p.pg = 12.36f;    // -> 12.4
    p.temp_c = -5.0f; // -> -5.0
    p.batt_v = 3.706f;// -> 3.71
    p.met_s = 0;

    const char *expected =
        "V:1 SYS:255 SRC:2 SEQ:65535 St:0 ALT:-123ft Max:20000ft "
        "G:0.9 Pg:12.4 T:-5.0C Batt:3.71V MET:0";

    char buf[128];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(expected, buf);
    TEST_ASSERT_EQUAL_size_t(strlen(expected), n);
}

// V is a constant 1 regardless of what else the struct carries.
void test_version_is_constant_one(void) {
    Packet p = golden_input();
    char buf[128];
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_INT(0, strncmp(buf, "V:1 ", 4));
}

// ---------------------------------------------------------------------------
// Additive per-axis accelerometer tags (Ax/Ay/Az) — ADR-0001 additive policy.
// New tags within v1: no V bump, appended after the canonical 12 so the golden
// vector stays byte-exact when they are absent.
// ---------------------------------------------------------------------------

// Absent by default: a Packet that does not opt in encodes exactly as before.
void test_axes_absent_by_default(void) {
    Packet p = golden_input();
    char buf[128];
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(GOLDEN, buf);
    TEST_ASSERT_NULL(strstr(buf, "Ax:"));
}

// Present: appended after MET, one decimal, same precision as G/Pg.
void test_axes_appended_when_present(void) {
    Packet p = golden_input();
    p.has_axes = true;
    p.ax = -1.2f;
    p.ay = 0.4f;
    p.az = 9.7f;

    const char *expected =
        "V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft "
        "G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12 Ax:-1.2 Ay:0.4 Az:9.7";

    char buf[128];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(expected, buf);
    TEST_ASSERT_EQUAL_size_t(strlen(expected), n);
}

// The 12 v1 tags are untouched by the addition — the golden prefix survives
// verbatim, which is what makes this additive rather than a grammar change.
void test_axes_do_not_disturb_the_v1_prefix(void) {
    Packet p = golden_input();
    p.has_axes = true;
    p.ax = 1.0f; p.ay = 2.0f; p.az = 3.0f;
    char buf[128];
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_INT(0, strncmp(buf, GOLDEN, strlen(GOLDEN)));
}

// Sign and rounding, including the -0.05 -> "-0.1" / "0.0" boundary behaviour.
void test_axes_signs_and_rounding(void) {
    Packet p = golden_input();
    p.has_axes = true;
    p.ax = -12.34f;   // -> -12.3
    p.ay = 0.04f;     // -> 0.0
    p.az = -0.04f;    // -> -0.0
    char buf[128];
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_NOT_NULL(strstr(buf, " Ax:-12.3 Ay:0.0 Az:-0.0"));
}

// Every field saturated, ADXL375 clipping at +/-200 g on all three axes: the
// widest frame the encoder can ever emit.
static Packet worst_case_input(void) {
    Packet p;
    p.sys = 255;
    p.src = 255;
    p.seq = 65535;
    p.state = 255;
    p.alt_ft = -99999;
    p.max_ft = -99999;
    p.g = -999.9f;
    p.pg = -999.9f;
    p.temp_c = -99.9f;
    p.batt_v = -99.99f;
    p.met_s = 65535;
    p.has_axes = true;
    p.ax = -200.0f;
    p.ay = -200.0f;
    p.az = -200.0f;
    return p;
}

// HEADROOM: the worst case must fit PACKET_BUF_LEN whole, with margin.
void test_worst_case_packet_fits_the_declared_buffer(void) {
    Packet p = worst_case_input();
    char buf[PACKET_BUF_LEN];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_size_t(strlen(buf), n);          // not truncated
    TEST_ASSERT_TRUE(n < sizeof(buf) - 1);             // fits, with the NUL
    TEST_ASSERT_TRUE(n + 8 <= PACKET_BUF_LEN);         // >= 8 bytes of headroom
}

// REGRESSION GUARD: pins why PACKET_BUF_LEN had to grow. The worst case does
// NOT fit the old 128-byte buffer — it truncates. Bounded, never an overflow,
// but trailing tags are lost, which is exactly what the wider buffer prevents.
// If someone shrinks PACKET_BUF_LEN back to 128, the test above fails.
void test_worst_case_would_truncate_in_the_old_128_buffer(void) {
    Packet p = worst_case_input();
    char buf[128];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_size_t(sizeof(buf) - 1, n);      // truncated at the edge
    TEST_ASSERT_EQUAL_size_t(n, strlen(buf));          // still NUL-terminated
}

// The typical in-flight frame is comfortable: the ADR golden vector plus axes.
void test_typical_frame_leaves_generous_headroom(void) {
    Packet p = golden_input();
    p.has_axes = true;
    p.ax = -1.2f; p.ay = 0.4f; p.az = 9.7f;
    char buf[PACKET_BUF_LEN];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_size_t(110, n);                  // 88 golden + 22 of axes
}

// Truncation stays safe with the axes enabled: never past the buffer, always
// NUL-terminated, and the reported length is the bytes actually written.
void test_axes_truncation_is_safe(void) {
    Packet p = golden_input();
    p.has_axes = true;
    p.ax = -1.2f; p.ay = 0.4f; p.az = 9.7f;

    char small[40];
    size_t n = encode_packet(p, small, sizeof(small));
    TEST_ASSERT_EQUAL_size_t(sizeof(small) - 1, n);
    TEST_ASSERT_EQUAL_size_t(n, strlen(small));      // NUL-terminated in bounds
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_encodes_golden_vector);
    RUN_TEST(test_encodes_second_fixture);
    RUN_TEST(test_version_is_constant_one);
    RUN_TEST(test_axes_absent_by_default);
    RUN_TEST(test_axes_appended_when_present);
    RUN_TEST(test_axes_do_not_disturb_the_v1_prefix);
    RUN_TEST(test_axes_signs_and_rounding);
    RUN_TEST(test_worst_case_packet_fits_the_declared_buffer);
    RUN_TEST(test_worst_case_would_truncate_in_the_old_128_buffer);
    RUN_TEST(test_typical_frame_leaves_generous_headroom);
    RUN_TEST(test_axes_truncation_is_safe);
    return UNITY_END();
}
