"""Ground ingest service — the single radio-owning process (D4).

The radio loop receives frames and hands each to IngestCore; a queue-backed
writer thread appends JSONL to a per-start session file so the radio loop never
blocks on disk (D1). Consumers register on the ObserverRegistry (logger is
implicit via the sink; OLED/dashboard register here). Clean shutdown on
SIGTERM/SIGINT writes a service_stop event and drains the queue.

Runs on the Pi:  python3 -m ground.ingest.service
Session logs:    $APOGEE_DATA (default ~/apogee-data/)
Field config:    $APOGEE_CONFIG (default ~/.config/apogee/ingest.json) — overrides
                 allowed_sys / known_src; NOT committed (SYS is field config).
"""
import json
import os
import queue
import secrets
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ground.rx.sx127x import SX127xRx, LoRaConfig
from ground.rx.transport import SpidevLgpioTransport
from ground.linkstats.linkstats import LinkStats
from ground.ingest.registry import ObserverRegistry
from ground.ingest.core import IngestCore
from ground.flights.live import LiveFlights
from ground.dashboard.model import LiveState, view_model, EventsRing
from ground.dashboard.app import serve, DASHBOARD_PORT
from ground.oled.render import oled_lines
from ground.oled.display import OledDisplay
from ground.panel.heartbeat import HeartbeatPublisher, state_snapshot, STATE_PATH
from ground.sessionlog.records import event_record, to_jsonl

DATA_DIR = Path(os.environ.get("APOGEE_DATA", str(Path.home() / "apogee-data")))
CONFIG_PATH = Path(os.environ.get("APOGEE_CONFIG", str(Path.home() / ".config/apogee/ingest.json")))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def session_filename(ts: str) -> str:
    """Session log name with a boot-unique random suffix so two starts in the same
    second can never collide and silently append two runs into one file — uniqueness
    by construction, independent of clock correctness."""
    return f"session-{ts}-{secrets.token_hex(3)}.jsonl"


def load_config() -> dict:
    cfg = {"allowed_sys": [7], "known_src": [1, 2], "callsign_binding": {}, "silence_timeout_s": 90}
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    except FileNotFoundError:
        pass
    # JSON object keys are strings; the CALL<->SYS binding is keyed by int SYS.
    cfg["callsign_binding"] = {int(k): v for k, v in cfg.get("callsign_binding", {}).items()}
    return cfg


class JsonlWriter(threading.Thread):
    """Drains a queue of JSONL lines to the session file off the radio thread."""

    def __init__(self, path: Path):
        super().__init__(daemon=True)
        self._q: queue.Queue = queue.Queue()
        self._f = open(path, "a", buffering=1)  # line-buffered
        self._stop = threading.Event()

    def sink(self, line: str) -> None:
        self._q.put(line)

    def run(self) -> None:
        while not self._stop.is_set() or not self._q.empty():
            try:
                self._f.write(self._q.get(timeout=0.2))
            except queue.Empty:
                continue

    def shutdown(self) -> None:
        self._stop.set()
        self.join(timeout=3)
        self._f.close()


def main() -> None:
    cfg = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session = session_filename(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    writer = JsonlWriter(DATA_DIR / session)
    writer.start()

    stats = LinkStats()
    registry = ObserverRegistry()
    events_ring = EventsRing()

    def sink(line):     # tee: durable JSONL log + a bounded ring for the dashboard events feed
        writer.sink(line)
        events_ring.capture(line)

    core = IngestCore(sink, stats, registry,
                      allowed_sys=cfg["allowed_sys"], known_src=cfg["known_src"],
                      callsign_binding=cfg["callsign_binding"])
    live = LiveFlights(sink, DATA_DIR / "flights-snapshot.json",
                       silence_timeout_s=cfg["silence_timeout_s"])
    registry.register(live.on_observation)
    live_state = LiveState()
    registry.register(live_state.update)

    sink(to_jsonl(event_record(now_iso(), "service_start", session=session, config=cfg)))
    print(f"[ingest] {DATA_DIR / session}  allowed_sys={cfg['allowed_sys']} known_src={cfg['known_src']}", flush=True)

    transport = SpidevLgpioTransport()
    rx = SX127xRx(transport, LoRaConfig())
    rx.configure()

    # Live dashboard: in-process daemon thread, reads immutable snapshots only —
    # never the radio/log; degrades silently if Flask is absent (never crashes the owner).
    start_mono = time.monotonic()

    def _view_model():
        up = max(1.0, time.monotonic() - start_mono)
        health = {"session": session, "uptime_s": round(up),
                  "decoded": core.decoded, "decode_errors": core.errors,
                  "crc_errors": getattr(rx, "crc_errors", 0),
                  "foreign": sum(core.foreign.values()), "anomalies": sum(core.anomalies.values()),
                  "packets_per_min": round(60.0 * core.decoded / up, 1)}
        return view_model(live_state.snapshot(), stats.snapshot(), live.open_flight_ids(),
                          health, events=events_ring.recent())

    def _serve():
        try:
            serve(_view_model)
        except Exception as exc:  # noqa: BLE001 — the dashboard must never take down the radio owner
            print(f"[ingest] dashboard off: {exc}", flush=True)

    threading.Thread(target=_serve, daemon=True).start()
    print(f"[ingest] dashboard on :{DASHBOARD_PORT}", flush=True)

    # Status OLED (Pi-only, I2C 0x3d). Construction probes the address; a missing or
    # failing OLED degrades silently and never touches the radio.
    oled = None
    try:
        oled = OledDisplay()
        print("[ingest] OLED on 0x3d", flush=True)
    except Exception as exc:  # noqa: BLE001 — OLED must never take down the radio owner
        print(f"[ingest] OLED off: {exc}", flush=True)

    def _oled_update(obs):
        if oled is None:
            return
        src = obs.packet.fields.get("SRC")
        panel = next((p for p in _view_model()["panels"] if p["src"] == src), None)
        if panel:
            oled.show(oled_lines(panel))

    if oled is not None:
        registry.register(_oled_update)

    # Heartbeat for the LED supervisor — ticked from INSIDE the RX loop (never a timer
    # thread), so it proves the loop is TURNING, not merely that the process is up. Publish
    # is fail-safe: a failure returns False and never escapes into the radio loop (the file
    # goes stale and the supervisor lights RED — correct degradation while capture continues).
    heartbeat = HeartbeatPublisher(STATE_PATH, log=lambda m: print(f"[ingest] {m}", flush=True))
    last_rx_iso = None       # wall time of the last ACCEPTED packet (core.decoded ticks)
    last_decoded = 0
    last_hb_mono = None      # monotonic gate for the ~1 Hz publish cadence

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    try:
        while not stop.is_set():
            now = now_iso()                      # wall time — what gets recorded
            mono = time.monotonic()              # monotonic — step-immune silence/duration
            frame = rx.receive()
            if frame:
                core.handle(frame.rssi_dbm, frame.payload, now, mono)
            else:
                time.sleep(0.02)
            for fl in live.tick(now, mono):      # cheap step-immune sweep; never blocks RX
                live_state.reset_baseline(fl.src)   # a closed flight resets its pad/AGL baseline
            if core.decoded != last_decoded:     # an accepted packet landed this turn
                last_rx_iso, last_decoded = now, core.decoded
            if last_hb_mono is None or mono - last_hb_mono >= 1.0:   # ~1 Hz, loop-driven
                heartbeat.publish(state_snapshot(
                    ts=now, last_rx_ts=last_rx_iso,
                    flight_open=bool(live.open_flight_ids())))
                last_hb_mono = mono
    finally:
        now = now_iso()
        for fl in live.tick(now, time.monotonic()):   # final sweep; still-open flights left OPEN
            live_state.reset_baseline(fl.src)
        sink(to_jsonl(event_record(
            now, "service_stop",
            decoded=core.decoded, errors=core.errors, foreign=core.foreign,
            anomalies={f"{k[0]}:{k[1]}": v for k, v in core.anomalies.items()})))
        writer.shutdown()
        transport.close()
        print("[ingest] stopped", flush=True)


if __name__ == "__main__":
    main()
