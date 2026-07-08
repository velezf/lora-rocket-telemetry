"""Host tests for service helpers (collision-proof session filenames)."""
import unittest

from ground.ingest.service import session_filename


class TestSessionFilename(unittest.TestCase):
    def test_unique_per_start_same_timestamp(self):
        a = session_filename("20260708T151541Z")
        b = session_filename("20260708T151541Z")
        self.assertNotEqual(a, b)   # two starts at the same second -> two distinct files

    def test_shape(self):
        name = session_filename("20260708T151541Z")
        self.assertTrue(name.startswith("session-20260708T151541Z-"))
        self.assertTrue(name.endswith(".jsonl"))


if __name__ == "__main__":
    unittest.main()
