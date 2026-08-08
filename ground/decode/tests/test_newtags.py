# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false
# ^ same rationale as test_v1.py: decode() union results accessed after runtime
#   type asserts, which pyright does not treat as narrowing.
"""Decoder tests for the ten additive tags decided 2026-08-08 (E+F frame shapes).

FLIGHT-frame additions: Vel, Gmx, Gmn, Wmx.
PAD-frame additions:    Vel, Gmx, Gmn, Gyx, Gyy, Gyz, Mgx, Mgy, Mgz.

All ten are unitless floats and mirror `G`/`Pg` exactly: no unit suffix, typed
float, exact-key lookup in `_V1_TAGS`. Additive per ADR 0001 — no version bump,
missing tags legal, and a frame with none of them decodes as before.

Worst forms + range assumptions (recorded with the fixtures, per the 2026-08-08
session decision):
    Vel:-1999.9   onboard vertical velocity ft/s, +/-1999.9
    Gmx:199.9     window max accel magnitude, g, 0-199.9
    Gmn:199.9     window MIN accel magnitude, g (worst FORM is longest, not the floor)
    Wmx:2293.8    window max gyro magnitude, dps (LSM6DSOX +/-2000 dps FS -> +/-2293.8)
    Gyx/Gyy/Gyz:-2293.8   raw gyro, dps, same FS
    Mgx/Mgy/Mgz:-478.9    raw mag, uT (LIS3MDL +/-4 gauss FS -> +/-478.9)
"""
import unittest

from ground.decode.v1 import decode, DecodedPacket, DecodeError

# ADR 0001 golden vector, unchanged — the 12-tag base every shape builds on.
BASE = b"V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12"

NEW_TAGS = ["Vel", "Gmx", "Gmn", "Wmx", "Gyx", "Gyy", "Gyz", "Mgx", "Mgy", "Mgz"]

# tag -> worst form value (the longest legal rendering under the range assumptions)
WORST = {
    "Vel": "-1999.9",
    "Gmx": "199.9",
    "Gmn": "199.9",
    "Wmx": "2293.8",
    "Gyx": "-2293.8", "Gyy": "-2293.8", "Gyz": "-2293.8",
    "Mgx": "-478.9", "Mgy": "-478.9", "Mgz": "-478.9",
}


class TestNewTagsTyped(unittest.TestCase):
    def test_each_new_tag_decodes_as_known_typed_float(self):
        for tag in NEW_TAGS:
            with self.subTest(tag=tag):
                r = decode(BASE + f" {tag}:{WORST[tag]}".encode())
                self.assertIsInstance(r, DecodedPacket)
                self.assertIn(tag, r.fields)            # KNOWN, not unknown
                self.assertNotIn(tag, r.unknown)
                self.assertIsInstance(r.fields[tag], float)
                self.assertAlmostEqual(r.fields[tag], float(WORST[tag]))

    def test_flight_shape_worst_form(self):
        """FLIGHT frame: base 12 + Vel + Gmx + Gmn + Wmx, all at worst form."""
        r = decode(BASE + b" Vel:-1999.9 Gmx:199.9 Gmn:199.9 Wmx:2293.8")
        self.assertIsInstance(r, DecodedPacket)
        self.assertAlmostEqual(r.fields["Vel"], -1999.9)
        self.assertAlmostEqual(r.fields["Gmx"], 199.9)
        self.assertAlmostEqual(r.fields["Gmn"], 199.9)
        self.assertAlmostEqual(r.fields["Wmx"], 2293.8)
        self.assertEqual(r.unknown, {})                 # every tag is known

    def test_pad_shape_worst_form(self):
        """PAD frame: base 12 + Vel + Gmx + Gmn + raw 9-DoF channels."""
        r = decode(BASE + b" Vel:-1999.9 Gmx:199.9 Gmn:199.9"
                          b" Gyx:-2293.8 Gyy:-2293.8 Gyz:-2293.8"
                          b" Mgx:-478.9 Mgy:-478.9 Mgz:-478.9")
        self.assertIsInstance(r, DecodedPacket)
        for tag in ("Gyx", "Gyy", "Gyz"):
            self.assertAlmostEqual(r.fields[tag], -2293.8)
        for tag in ("Mgx", "Mgy", "Mgz"):
            self.assertAlmostEqual(r.fields[tag], -478.9)
        self.assertEqual(r.unknown, {})

    def test_frame_without_new_tags_still_decodes(self):
        """Missing tags are legal (ADR 0001): the pre-change golden is untouched."""
        r = decode(BASE)
        self.assertIsInstance(r, DecodedPacket)
        for tag in NEW_TAGS:
            self.assertNotIn(tag, r.fields)
            self.assertNotIn(tag, r.unknown)
        self.assertEqual(r.fields["SEQ"], 42)

    def test_malformed_new_tag_value_same_error_class_as_old(self):
        """A junk value in a new tag returns the SAME DecodeError reason a junk
        value in an old tag does — new tags ride the one typed-parse path."""
        old = decode(b"V:1 G:abc")
        self.assertIsInstance(old, DecodeError)
        self.assertEqual(old.reason, "bad-value")
        for tag in NEW_TAGS:
            with self.subTest(tag=tag):
                r = decode(f"V:1 {tag}:abc".encode())
                self.assertIsInstance(r, DecodeError)
                self.assertEqual(r.reason, old.reason)


if __name__ == "__main__":
    unittest.main()
