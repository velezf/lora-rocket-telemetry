#include <unity.h>
void setUp(void) {}
void tearDown(void) {}
void test_harness_is_wired(void) {
    TEST_ASSERT_EQUAL_INT(4, 2 + 2);
}
int main(int, char **) {
    UNITY_BEGIN();
    RUN_TEST(test_harness_is_wired);
    return UNITY_END();
}
