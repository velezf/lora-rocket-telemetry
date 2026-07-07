"""Epic 4.2 session-log record builders — pure/deterministic tests.

Run from repo root:  python3 -m unittest ground.sessionlog.tests.test_records
"""
import json
import unittest

from ground.decode.v1 import decode, DecodedPacket
from ground.sessionlog.records import packet_record, event_record, to_jsonl


class PacketRecordTests(unittest.TestCase):
    def test_golden_packet(self):
        raw = b"V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12"
        decoded = decode(raw)
        self.assertIsInstance(decoded, DecodedPacket)

        rec = packet_record("2026-07-07T12:00:00.123", -42, decoded)

        self.assertEqual(rec["type"], "packet")
        self.assertEqual(rec["received_at"], "2026-07-07T12:00:00.123")
        self.assertEqual(rec["rssi"], -42)
        self.assertEqual(rec["sys"], 7)
        self.assertEqual(rec["src"], 1)
        self.assertEqual(rec["seq"], 42)
        # raw preserved verbatim so history can be re-decoded later
        self.assertEqual(rec["raw"], raw.decode("ascii"))
        # full decoded fields carried through
        self.assertEqual(rec["fields"], decoded.fields)
        self.assertEqual(rec["fields"]["ALT"], 1234)
        self.assertEqual(rec["fields"]["T"], 21.5)
        self.assertEqual(rec["unknown"], {})

    def test_unknown_tag_preserved(self):
        raw = b"V:1 SYS:7 SRC:1 SEQ:42 Roll:5.2"
        decoded = decode(raw)
        self.assertIsInstance(decoded, DecodedPacket)

        rec = packet_record("2026-07-07T12:00:01.000", -55, decoded)

        self.assertEqual(rec["unknown"], {"Roll": "5.2"})
        self.assertEqual(rec["unknown"], decoded.unknown)
        self.assertEqual(rec["raw"], raw.decode("ascii"))

    def test_missing_optional_tags_are_none(self):
        decoded = decode(b"V:1 ALT:100ft")
        self.assertIsInstance(decoded, DecodedPacket)

        rec = packet_record("2026-07-07T12:00:02.000", None, decoded)

        self.assertIsNone(rec["sys"])
        self.assertIsNone(rec["src"])
        self.assertIsNone(rec["seq"])
        self.assertEqual(rec["fields"]["ALT"], 100)


class EventRecordTests(unittest.TestCase):
    def test_flight_open_round_trips_detail(self):
        rec = event_record("2026-07-07T12:00:00.000", "flight_open", flight_id="2026-07-07-F1")

        self.assertEqual(rec["type"], "event")
        self.assertEqual(rec["received_at"], "2026-07-07T12:00:00.000")
        self.assertEqual(rec["event"], "flight_open")
        self.assertEqual(rec["flight_id"], "2026-07-07-F1")

    def test_event_without_detail(self):
        rec = event_record("2026-07-07T12:00:00.000", "service_start")
        self.assertEqual(rec["type"], "event")
        self.assertEqual(rec["event"], "service_start")


class ToJsonlTests(unittest.TestCase):
    def test_ends_with_newline_and_round_trips(self):
        decoded = decode(b"V:1 SYS:7 SRC:1 SEQ:42 ALT:1234ft")
        rec = packet_record("2026-07-07T12:00:00.123", -42, decoded)

        line = to_jsonl(rec)

        self.assertTrue(line.endswith("\n"))
        self.assertEqual(json.loads(line), rec)

    def test_event_round_trips(self):
        rec = event_record("2026-07-07T12:00:00.000", "annotation", note="liftoff looked nominal")
        line = to_jsonl(rec)
        self.assertTrue(line.endswith("\n"))
        self.assertEqual(json.loads(line), rec)


if __name__ == "__main__":
    unittest.main()
