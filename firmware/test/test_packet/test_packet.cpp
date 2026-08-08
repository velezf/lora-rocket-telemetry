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

// --- TRUNCATION IS LOUD (Phase 2 item 1). The old contract returned out_len-1 on
// overflow — a valid-looking length — and the fragment went to air: a frame cut at
// 105 B decoded as a VALID packet with MET:6 where the truth was 65535. The new
// contract: encode_packet returns 0 on ANY truncation, out[0]=='\0'. No real frame is
// 0 bytes, so 0 is unambiguous, and a caller that ignores it sends nothing rather than
// a lie.

static Packet saturated_packet() {
    Packet p;
    p.sys = 255; p.src = 255; p.seq = 65535; p.state = 3;
    p.alt_ft = -19999; p.max_ft = 199999;
    p.g = -199.9f; p.pg = 199.9f; p.temp_c = -99.9f; p.batt_v = 99.99f;
    p.met_s = 65535;
    return p;
}

void test_exact_fit_succeeds(void) {
    Packet p = saturated_packet();
    char big[512];
    size_t need = encode_packet(p, big, sizeof(big));   // true length, roomy buffer
    TEST_ASSERT_TRUE(need > 0);

    char exact[512];
    size_t n = encode_packet(p, exact, need + 1);       // exactly frame + NUL
    TEST_ASSERT_EQUAL_UINT(need, n);
    TEST_ASSERT_EQUAL_STRING(big, exact);
}

void test_one_byte_short_is_LOUD_not_a_fragment(void) {
    Packet p = saturated_packet();
    char big[512];
    size_t need = encode_packet(p, big, sizeof(big));

    char tight[512];
    size_t n = encode_packet(p, tight, need);           // one byte too small
    TEST_ASSERT_EQUAL_UINT(0, n);                       // LOUD: zero, not need-1
    TEST_ASSERT_EQUAL_STRING("", tight);                // and no partial frame visible
}

void test_hopelessly_small_buffer_is_loud(void) {
    Packet p = saturated_packet();
    char tiny[8];
    TEST_ASSERT_EQUAL_UINT(0, encode_packet(p, tiny, sizeof(tiny)));
    TEST_ASSERT_EQUAL_STRING("", tiny);
}

int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_encodes_golden_vector);
    RUN_TEST(test_encodes_second_fixture);
    RUN_TEST(test_version_is_constant_one);
    RUN_TEST(test_exact_fit_succeeds);
    RUN_TEST(test_one_byte_short_is_LOUD_not_a_fragment);
    RUN_TEST(test_hopelessly_small_buffer_is_loud);
    return UNITY_END();
}
