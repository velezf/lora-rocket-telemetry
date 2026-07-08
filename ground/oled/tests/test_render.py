"""Host tests for the pure OLED render (panel dict -> display lines)."""
import unittest

from ground.oled.render import oled_lines


class TestOledRender(unittest.TestCase):
    def test_in_flight_panel(self):
        panel = {"src": 1, "callsign": "KC3ZTQ", "altitude_ft": 500, "peak_ft": 500,
                 "state": "ascent", "rssi": -60, "seq_loss_pct": 0.0,
                 "flight_id": "2026-07-08-F1", "flight_open": True}
        lines = oled_lines(panel)
        self.assertEqual(len(lines), 4)
        self.assertIn("SRC:1", lines[0])
        self.assertIn("KC3ZTQ", lines[0])
        self.assertIn("500", lines[1])
        self.assertIn("ASCENT", lines[2])
        self.assertIn("F1", lines[2])          # short flight tag
        self.assertIn("-60", lines[3])

    def test_idle_panel_no_callsign(self):
        panel = {"src": 2, "callsign": None, "altitude_ft": 0, "peak_ft": 0,
                 "state": "pad", "rssi": -70, "seq_loss_pct": 0.0,
                 "flight_id": None, "flight_open": False}
        lines = oled_lines(panel)
        self.assertEqual(lines[0], "SRC:2")    # no trailing callsign
        self.assertIn("PAD", lines[2])
        self.assertIn("idle", lines[2])

    def test_missing_values_show_placeholder(self):
        lines = oled_lines({"src": 1, "altitude_ft": None, "peak_ft": None})
        self.assertIn("--", lines[1])
        self.assertEqual(len(lines), 4)


if __name__ == "__main__":
    unittest.main()
