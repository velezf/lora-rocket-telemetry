"""The BOTH-ENDS RF constants cannot drift apart silently.

Authority: docs/adr/0005-telemetry-rate-and-rf-configuration.md (§7) — a
bandwidth/SF/CR/frequency mismatch between the sled and the ground station
fails as SILENT total link loss: no error, simply no packets. Prose asks each
end to cite the ADR; this test is the mechanical half — it reads the SLED's
constants (firmware/lib/rfconfig/rf_config.h) and compares them against the
ground station's deployed defaults (LoRaConfig), so changing either end alone
fails a test instead of failing at the bench with a dead link.

This is a CROSS-END check, not a restatement pin: it can fail on a real
divergence of the two artifacts, whichever side moved.
"""
import re
import unittest
from pathlib import Path

from ground.rx.sx127x import LoRaConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
RF_CONFIG_H = REPO_ROOT / "firmware" / "lib" / "rfconfig" / "rf_config.h"

_CONST_RE = r"constexpr\s+[a-z ]+\s+{name}\s*=\s*(\d+)"


def _read_const(text: str, name: str) -> int:
    m = re.search(_CONST_RE.format(name=name), text)
    if m is None:
        raise AssertionError(f"{name} not found in {RF_CONFIG_H}")
    return int(m.group(1))


class TestBothEndsRfConstantsAgree(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            RF_CONFIG_H.is_file(),
            f"sled RF constants header missing at {RF_CONFIG_H} — the cross-end "
            "check has nothing to check against (this is a FAILURE, not a skip: "
            "a guard that silently stops guarding is the hollow-check class)",
        )
        self.text = RF_CONFIG_H.read_text()
        self.ground = LoRaConfig()   # the deployed default (ground/ingest/service.py)

    def test_bandwidth_matches(self):
        self.assertEqual(_read_const(self.text, "BANDWIDTH_KHZ"),
                         int(self.ground.bandwidth_khz))

    def test_spreading_factor_matches(self):
        self.assertEqual(_read_const(self.text, "SPREADING_FACTOR"),
                         self.ground.spreading_factor)

    def test_coding_rate_matches(self):
        self.assertEqual(_read_const(self.text, "CODING_RATE_DENOM"),
                         self.ground.coding_rate)

    def test_frequency_matches(self):
        self.assertEqual(_read_const(self.text, "FREQ_HZ"), self.ground.freq_hz)

    def test_tx_power_is_the_adr0005_value(self):
        # TX power has no ground-side twin (RX only); its authority is ADR 0005
        # §2 — 17 dBm, decided WITH the bandwidth change (thermal at 58.9 % duty),
        # not separately. 23 dBm here means the sled kept the pre-ADR power.
        self.assertEqual(_read_const(self.text, "TX_POWER_DBM"), 17)


class TestTheParserCanFail(unittest.TestCase):
    """Anti-hollow: the header parser must be able to MISS — a renamed or
    deleted constant raises instead of silently comparing nothing."""

    def test_missing_constant_raises(self):
        with self.assertRaises(AssertionError):
            _read_const("constexpr unsigned OTHER = 1;", "BANDWIDTH_KHZ")

    def test_present_constant_is_read(self):
        self.assertEqual(
            _read_const("constexpr unsigned BANDWIDTH_KHZ = 500;", "BANDWIDTH_KHZ"),
            500)


if __name__ == "__main__":
    unittest.main()
