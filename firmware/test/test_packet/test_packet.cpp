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
// St:1 -> FLIGHT shape: base + Wmx (E+F split, ADR 0005 A1.3). The shape is DERIVED
// from St inside the encoder — there is no shape field to disagree with the state.
static const char *GOLDEN_EXT =
    "V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft "
    "G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12 Vel:88.2 Gmx:9.1 Gmn:0.9 Wmx:47.2";

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
    p.wmx = 47.2f;
    p.gyx = 1.1f; p.gyy = -0.4f; p.gyz = 0.2f;     // ignored: St:1 is flight shape
    p.mgx = 23.0f; p.mgy = -41.5f; p.mgz = 7.8f;   // ignored: St:1 is flight shape
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
    p.wmx = 999.9f;      // ignored: St:0 is PAD shape — no Wmx on pad frames
    p.gyx = 1.14f; p.gyy = -0.45f; p.gyz = 0.0f;   // -> 1.1 -0.4 0.0
    p.mgx = 23.04f; p.mgy = -41.54f; p.mgz = 478.9f;   // -> 23.0 -41.5 478.9

    // St:0 -> PAD shape: base + raw 9-DoF channels, no Wmx (A1.3 — the pad frame
    // is Epic 5's calibration record).
    const char *expected =
        "V:1 SYS:255 SRC:2 SEQ:65535 St:0 ALT:-123ft Max:20000ft "
        "G:0.9 Pg:12.4 T:-5.0C Batt:3.71V MET:0 Vel:-32.8 Gmx:199.9 Gmn:0.1 "
        "Gyx:1.1 Gyy:-0.4 Gyz:0.0 Mgx:23.0 Mgy:-41.5 Mgz:478.9";

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
    p.sys = 255; p.src = 255; p.seq = 65535; p.state = 2;
    p.alt_ft = -19999; p.max_ft = 199999;
    p.g = 199.9f; p.pg = 199.9f; p.temp_c = -99.9f; p.batt_v = 99.99f;
    p.met_s = 65535;
    p.vel_fps = -1999.9f;   // A1.4 worst form
    p.gmx = 199.9f;
    p.gmn = 199.9f;         // worst FORM is the longest, not the value floor (A1.4)
    p.wmx = 2293.8f;        // LSM6DSOX ±2000 dps FS reports to ±2293.8
    p.gyx = p.gyy = p.gyz = -2293.8f;
    p.mgx = p.mgy = p.mgz = -478.9f;
    return p;
}

// --- CROSS-LANGUAGE GOLDENS: the ground decoder's worst-frame fixtures
// (ground/flights/tests/fixtures/newtags_worst_frames.jsonl, merged 8bad30c) carry
// the exact raw strings both ends must agree on. The C encoder reproduces them
// byte-for-byte — the same frames the Python decoder is already pinned against. ---

void test_flight_shape_matches_ground_fixture_byte_for_byte(void) {
    Packet p = saturated_packet();          // St:2 -> flight shape
    const char *fixture =
        "V:1 SYS:255 SRC:255 SEQ:65535 St:2 ALT:-19999ft Max:199999ft "
        "G:199.9 Pg:199.9 T:-99.9C Batt:99.99V MET:65535 "
        "Vel:-1999.9 Gmx:199.9 Gmn:199.9 Wmx:2293.8";
    char buf[512];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(fixture, buf);
    TEST_ASSERT_EQUAL_UINT(strlen(fixture), n);
}

void test_pad_shape_matches_ground_fixture_byte_for_byte(void) {
    Packet p = saturated_packet();
    p.state = 0;                            // St:0 -> pad shape
    const char *fixture =
        "V:1 SYS:255 SRC:255 SEQ:65535 St:0 ALT:-19999ft Max:199999ft "
        "G:199.9 Pg:199.9 T:-99.9C Batt:99.99V MET:65535 "
        "Vel:-1999.9 Gmx:199.9 Gmn:199.9 "
        "Gyx:-2293.8 Gyy:-2293.8 Gyz:-2293.8 Mgx:-478.9 Mgy:-478.9 Mgz:-478.9";
    char buf[512];
    size_t n = encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(fixture, buf);
    TEST_ASSERT_EQUAL_UINT(strlen(fixture), n);
}

// A1.4 worst-case sizes: FLIGHT 152 B, PAD 210 B (supersedes the pre-9DoF 141 B pin).
// The worst FORM of G is the NEGATIVE bound (-199.9 — one byte longer than the
// fixture's 199.9, which is why the fixture strings measure 151/209). If a range
// assumption grows, the A1.4 table, these pins and the msg[] size in src/main.cpp
// move together — these tests make that drift loud.
void test_worst_case_sizes_per_adr0005_a14(void) {
    Packet p = saturated_packet();
    p.g = -199.9f;                          // worst form, not worst value
    char buf[512];
    TEST_ASSERT_EQUAL_UINT(152, encode_packet(p, buf, sizeof(buf)));   // flight
    p.state = 0;
    TEST_ASSERT_EQUAL_UINT(210, encode_packet(p, buf, sizeof(buf)));   // pad
}

// The shape follows St and ONLY St: flight frames carry Wmx and no raw channels;
// pad frames carry raw channels and no Wmx. Both assertions in both directions,
// so a tail emitted unconditionally cannot pass.
void test_shape_follows_state(void) {
    Packet p = saturated_packet();
    char buf[512];
    p.state = 1;
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_NOT_NULL(strstr(buf, " Wmx:"));
    TEST_ASSERT_NULL(strstr(buf, " Gyx:"));
    TEST_ASSERT_NULL(strstr(buf, " Mgx:"));
    p.state = 0;
    encode_packet(p, buf, sizeof(buf));
    TEST_ASSERT_NULL(strstr(buf, " Wmx:"));
    TEST_ASSERT_NOT_NULL(strstr(buf, " Gyx:"));
    TEST_ASSERT_NOT_NULL(strstr(buf, " Mgx:"));
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
    RUN_TEST(test_flight_shape_matches_ground_fixture_byte_for_byte);
    RUN_TEST(test_pad_shape_matches_ground_fixture_byte_for_byte);
    RUN_TEST(test_worst_case_sizes_per_adr0005_a14);
    RUN_TEST(test_shape_follows_state);
    RUN_TEST(test_version_is_constant_one);
    RUN_TEST(test_exact_fit_succeeds);
    RUN_TEST(test_one_byte_short_is_LOUD_not_a_fragment);
    RUN_TEST(test_hopelessly_small_buffer_is_loud);
    return UNITY_END();
}
