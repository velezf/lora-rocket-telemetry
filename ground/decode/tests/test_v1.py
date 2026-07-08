# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportArgumentType=false
# ^ tests intentionally access decode() union results after asserting the type at
#   runtime; pyright doesn't treat unittest.assertIsInstance as a narrowing guard.
"""Host tests for the ADR-0001 v1 packet decoder.

Pure Python, no radio/I-O imports — must pass on both Mac and Pi
(`python3 -m unittest`). Mirrors the discipline of firmware/lib and asserts the
additive-extension policy from ADR 0001. Malformed input returns a structured
DecodeError; decode() never raises.
"""
import unittest

from ground.decode.v1 import decode, DecodedPacket, DecodeError

# ADR 0001 canonical golden vector
GOLDEN = b"V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12"


class TestGolden(unittest.TestCase):
    def test_all_fields_typed(self):
        r = decode(GOLDEN)
        self.assertIsInstance(r, DecodedPacket)
        self.assertTrue(r.ok)
        self.assertEqual(r.version, 1)
        self.assertEqual(r.fields["SYS"], 7)
        self.assertEqual(r.fields["SRC"], 1)
        self.assertEqual(r.fields["SEQ"], 42)
        self.assertEqual(r.fields["St"], 1)
        self.assertEqual(r.fields["ALT"], 1234)
        self.assertEqual(r.fields["Max"], 5678)
        self.assertAlmostEqual(r.fields["G"], 2.3)
        self.assertAlmostEqual(r.fields["Pg"], 9.1)
        self.assertAlmostEqual(r.fields["T"], 21.5)
        self.assertAlmostEqual(r.fields["Batt"], 3.92)
        self.assertEqual(r.fields["MET"], 12)
        self.assertEqual(r.unknown, {})

    def test_numeric_types(self):
        r = decode(GOLDEN)
        self.assertIsInstance(r.fields["ALT"], int)
        self.assertIsInstance(r.fields["G"], float)

    def test_negative_values(self):
        r = decode(b"V:1 SRC:1 ALT:-83ft T:-5.0C")
        self.assertEqual(r.fields["ALT"], -83)
        self.assertAlmostEqual(r.fields["T"], -5.0)

    def test_accepts_str_and_bytes(self):
        self.assertIsInstance(decode(GOLDEN.decode()), DecodedPacket)


class TestAdditiveExtension(unittest.TestCase):
    def test_unknown_tags_tolerated_and_surfaced(self):
        r = decode(GOLDEN + b" Roll:5.2 Spin:12")
        self.assertIsInstance(r, DecodedPacket)          # NOT an error
        self.assertEqual(r.fields["SEQ"], 42)            # known still decoded
        self.assertEqual(r.unknown, {"Roll": "5.2", "Spin": "12"})  # raw, surfaced

    def test_missing_tags_tolerated(self):
        # lander-style subset (SRC:2), sled-only tags absent
        r = decode(b"V:1 SYS:7 SRC:2 SEQ:3 T:19.0C Batt:3.80V")
        self.assertIsInstance(r, DecodedPacket)
        self.assertEqual(r.fields["SRC"], 2)
        self.assertNotIn("ALT", r.fields)                # absent is valid, not an error

    def test_callsign_tag_surfaced_as_unknown(self):
        # Part-97 station ID: CALL rides the additive/unknown-tag path
        r = decode(GOLDEN + b" CALL:KC3ZTQ")
        self.assertIsInstance(r, DecodedPacket)
        self.assertEqual(r.unknown["CALL"], "KC3ZTQ")
        self.assertEqual(r.fields["SEQ"], 42)            # known fields still decoded


class TestErrors(unittest.TestCase):
    def _err(self, payload, reason):
        r = decode(payload)
        self.assertIsInstance(r, DecodeError, f"{payload!r} should be a DecodeError")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, reason)

    def test_empty(self):               self._err(b"", "empty")
    def test_whitespace_only(self):     self._err(b"   ", "empty")
    def test_no_version_first(self):    self._err(b"SYS:7 V:1", "no-version")
    def test_wrong_version(self):       self._err(b"V:2 SYS:7 SRC:1", "unsupported-version")
    def test_bare_token(self):          self._err(b"V:1 SYS:7 GARBAGE", "malformed-token")
    def test_truncated_empty_value(self): self._err(b"V:1 SRC:", "malformed-token")
    def test_double_colon(self):        self._err(b"V:1 T:2:5", "malformed-token")
    def test_bad_int_value(self):       self._err(b"V:1 SEQ:abc", "bad-value")
    def test_non_ascii(self):           self._err(b"V:1 \xff\xfe", "not-ascii")

    def test_never_raises_on_junk(self):
        junk = [b"", b"\x00\x01", b"V:", b":", b"V:1 :", b"V:1 X:", b"garbage",
                b"V:1 " + b"A" * 300, b"V", b"V:1 ALT:ft"]
        for p in junk:
            try:
                r = decode(p)
            except Exception as exc:  # noqa: BLE001 — the whole point is it must not raise
                self.fail(f"decode raised on {p!r}: {exc!r}")
            self.assertIn(r.ok, (True, False))


if __name__ == "__main__":
    unittest.main()
