"""RX glue: LoRaConfig -> adafruit_rfm9x settings, payload -> view-model.

The RF constants have ONE authority — `ground/rx/sx127x.py::LoRaConfig`
(itself citing ADR 0005 §7). The mapping tests use a NON-default config so
the unit conversions can actually fail; the flight-default test then pins
the mapped values against ADR 0005's literal numbers, which is deliberate
restatement-as-evidence: a cross-end check needs an independent statement
of the contract, not a read-back of the same variable.
"""
from ground.decode.v1 import decode  # noqa: F401  (contract import sanity)
from ground.rx.sx127x import LoRaConfig

from handheld.app.rx import RxCounters, apply_settings, handle_payload, rfm9x_settings
from handheld.app.viewmodel import HandheldModel


def test_mapping_converts_units_from_a_nondefault_config():
    cfg = LoRaConfig(freq_hz=433_500_000, bandwidth_khz=125,
                     spreading_factor=9, coding_rate=8, preamble=6, crc=False)
    s = rfm9x_settings(cfg)
    assert s["frequency_mhz"] == 433.5          # Hz -> MHz
    assert s["signal_bandwidth"] == 125_000     # kHz -> Hz
    assert s["spreading_factor"] == 9
    assert s["coding_rate"] == 8
    assert s["preamble_length"] == 6
    assert s["enable_crc"] is False


def test_flight_defaults_match_adr_0005():
    s = rfm9x_settings(LoRaConfig())
    # independent restatement of ADR 0005 §7 / §1 — the cross-end contract
    assert s["frequency_mhz"] == 434.0
    assert s["signal_bandwidth"] == 500_000
    assert s["spreading_factor"] == 7
    assert s["coding_rate"] == 5
    assert s["enable_crc"] is True


def test_apply_settings_sets_every_mapped_property():
    class Dummy:
        pass

    radio = Dummy()
    cfg = LoRaConfig()
    apply_settings(radio, cfg)
    for key, val in rfm9x_settings(cfg).items():
        assert getattr(radio, key) == val


def test_valid_payload_reaches_the_model():
    m = HandheldModel()
    c = RxCounters()
    ok = handle_payload(m, b"V:1 SYS:7 SRC:1 SEQ:3 St:0 ALT:5ft MET:0",
                        rssi_dbm=-48.0, mono=2.0, counters=c)
    assert ok
    v = m.snapshot(mono=2.1)
    assert v.mode == "live" and v.alt_ft == 5
    assert c.accepted == 1 and c.decode_errors == 0


def test_garbage_is_counted_never_raised_and_model_untouched():
    m = HandheldModel()
    c = RxCounters()
    ok = handle_payload(m, b"\xff\xfe not a packet", rssi_dbm=-48.0,
                        mono=2.0, counters=c)
    assert not ok
    assert m.snapshot(mono=2.1).mode == "idle"
    assert c.decode_errors == 1 and c.accepted == 0


def test_foreign_sys_counts_as_rejected_not_error():
    m = HandheldModel()
    c = RxCounters()
    ok = handle_payload(m, b"V:1 SYS:3 SRC:1 SEQ:3 St:0 ALT:5ft",
                        rssi_dbm=-48.0, mono=2.0, counters=c)
    assert not ok
    assert c.decode_errors == 0 and c.accepted == 0
    assert m.foreign_sys == 1
