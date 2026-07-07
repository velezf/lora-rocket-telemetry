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

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_encodes_golden_vector);
    RUN_TEST(test_encodes_second_fixture);
    RUN_TEST(test_version_is_constant_one);
    return UNITY_END();
}
