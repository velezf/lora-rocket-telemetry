"""Loop layer (Epic 8.2 slice 4): rx_step / render_tick / display wrapper.

These encode the ground OLED lessons as FAILING-CAPABLE tests rather than
remembered conventions (docs/RESUME.md "What the OLED fix taught"):
- the recovery preamble ships on EVERY frame (a reset SSD1306 still ACKs,
  so there is nothing to trigger on), and it must NOT contain 0xAE — that
  byte is cold-start hygiene and was the once-a-second flash defect;
- a display fault is counted and survived, never allowed to stop the loop;
- the renderer redraws periodically with no new data (quiet pad != dead).
"""
from handheld.app.loop import LoopCounters, render_tick, rx_step
from handheld.app.oled import SSD1306_RECOVERY_PREAMBLE, HeartbeatDisplay
from handheld.app.rx import RxCounters
from handheld.app.viewmodel import HandheldModel


class FakeSSD:
    """Duck-typed adafruit_ssd1306 surface: write_cmd/image/show."""
    def __init__(self, fail_after=None):
        self.cmds = []
        self.images = []
        self.shows = 0
        self._fail_after = fail_after

    def write_cmd(self, b):
        self.cmds.append(b)

    def image(self, img):
        self.images.append(img)

    def show(self):
        if self._fail_after is not None and self.shows >= self._fail_after:
            raise OSError("I2C EIO")
        self.shows += 1


class FakeRadio:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.last_rssi = -47.0

    def receive(self, **kw):
        return self._payloads.pop(0) if self._payloads else None


def test_recovery_preamble_has_display_on_and_never_0xae():
    assert 0xAF in SSD1306_RECOVERY_PREAMBLE
    assert 0xAE not in SSD1306_RECOVERY_PREAMBLE   # the flash defect, pinned


def test_preamble_ships_on_every_show_unconditionally():
    ssd = FakeSSD()
    disp = HeartbeatDisplay(ssd)
    model = HandheldModel()
    c = LoopCounters()
    render_tick(model, disp, mono=1.0, counters=c)
    render_tick(model, disp, mono=2.0, counters=c)   # no new data: still draws
    assert ssd.shows == 2
    assert ssd.cmds.count(0xAF) == 2                 # preamble every frame
    assert c.render_errors == 0


def test_display_fault_is_counted_and_survived():
    ssd = FakeSSD(fail_after=1)
    disp = HeartbeatDisplay(ssd)
    model = HandheldModel()
    c = LoopCounters()
    render_tick(model, disp, mono=1.0, counters=c)
    render_tick(model, disp, mono=2.0, counters=c)   # raises inside: survived
    render_tick(model, disp, mono=3.0, counters=c)
    assert c.render_errors == 2
    assert ssd.shows == 1


def test_rx_step_feeds_model_and_reports_rssi():
    radio = FakeRadio([b"V:1 SYS:7 SRC:1 SEQ:1 St:0 ALT:4ft MET:0"])
    model = HandheldModel()
    rc, lc = RxCounters(), LoopCounters()
    rx_step(radio, model, mono=5.0, rx_counters=rc, counters=lc)
    v = model.snapshot(mono=5.1)
    assert v.mode == "live" and v.alt_ft == 4 and v.rssi_dbm == -47.0
    assert rc.accepted == 1


def test_rx_step_quiet_and_faulting_radio_are_survived():
    model = HandheldModel()
    rc, lc = RxCounters(), LoopCounters()
    rx_step(FakeRadio([]), model, mono=1.0, rx_counters=rc, counters=lc)
    assert model.snapshot(mono=1.1).mode == "idle"

    class BrokenRadio:
        last_rssi = 0.0
        def receive(self, **kw):
            raise RuntimeError("SPI wedge")

    rx_step(BrokenRadio(), model, mono=2.0, rx_counters=rc, counters=lc)
    assert lc.rx_errors == 1                          # counted, not raised
