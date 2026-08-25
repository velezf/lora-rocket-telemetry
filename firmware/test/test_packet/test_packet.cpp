#include <unity.h>
#include <cstring>
#include "packet.h"

void setUp(void) {}
void tearDown(void) {}

// Golden vector from docs/adr/0001-packet-format-v1.md (single source of truth).
// The 12-tag ADR golden stays byte-identical as a PREFIX; Vel/Gmx/Gmn are additive
// tags appended after MET (ADR 0005 A1.4 — order pinned by the merged decoder
// fixtures, ground/flights/tests/fixtures/newtags_worst_frames.jsonl).
static const char *GOLDEN =
    "V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft "
    "G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12";
static const char *GOLDEN_EXT =
    "V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft "
    "G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12 Vel:88.2 Gmx:9.1 Gmn:0.9";

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
    p.vel_fps = 88.2f;
    p.gmx = 9.1f;
    p.gmn = 0.9f;
    return p;
}

// The encoder reproduces the extended frame byte-for-byte...
void test_encodes_golden_vector(void) {
    Packet p = golden_input();
    char buf[192];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(GOLDEN_EXT, buf);
    TEST_ASSERT_EQUAL_size_t(strlen(GOLDEN_EXT), n);
}

// ...and the ADR 0001 12-tag golden survives as an exact byte prefix — the additive
// contract means old fields keep their order, form and precision to the byte.
void test_adr_golden_is_an_exact_prefix(void) {
    Packet p = golden_input();
    char buf[192];
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_INT(0, strncmp(buf, GOLDEN, strlen(GOLDEN)));
    TEST_ASSERT_EQUAL_CHAR(' ', buf[strlen(GOLDEN)]);   // then a delimiter, not a digit
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
    p.vel_fps = -32.75f; // -> -32.8 (may be negative: descent)
    p.gmx = 199.94f;     // -> 199.9
    p.gmn = 0.05f;       // -> 0.1

    const char *expected =
        "V:1 SYS:255 SRC:2 SEQ:65535 St:0 ALT:-123ft Max:20000ft "
        "G:0.9 Pg:12.4 T:-5.0C Batt:3.71V MET:0 Vel:-32.8 Gmx:199.9 Gmn:0.1";

    char buf[192];
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
    p.vel_fps = -1999.9f;   // A1.4 worst form
    p.gmx = 199.9f;
    p.gmn = 199.9f;         // worst FORM is the longest, not the value floor (A1.4)
    return p;
}

// ADR 0005 §4 / A1.4: the worst-case frame with Vel/Gmx/Gmn is 141 B (109 + 12 + 10
// + 10). If a field's range assumption grows, this number, the A1.4 table and the
// msg[] size in src/main.cpp move together — this test is what makes that drift loud.
void test_worst_case_frame_is_141_bytes_per_adr0005(void) {
    Packet p = saturated_packet();
    char buf[512];
    TEST_ASSERT_EQUAL_UINT(141, encode_packet(p, buf, sizeof(buf)));
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
    RUN_TEST(test_adr_golden_is_an_exact_prefix);
    RUN_TEST(test_encodes_second_fixture);
    RUN_TEST(test_worst_case_frame_is_141_bytes_per_adr0005);
    RUN_TEST(test_version_is_constant_one);
    RUN_TEST(test_exact_fit_succeeds);
    RUN_TEST(test_one_byte_short_is_LOUD_not_a_fragment);
    RUN_TEST(test_hopelessly_small_buffer_is_loud);
    return UNITY_END();
}
