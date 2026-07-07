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
from ground.sessionlog.records import event_record, to_jsonl

DATA_DIR = Path(os.environ.get("APOGEE_DATA", str(Path.home() / "apogee-data")))
CONFIG_PATH = Path(os.environ.get("APOGEE_CONFIG", str(Path.home() / ".config/apogee/ingest.json")))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_config() -> dict:
    cfg = {"allowed_sys": [7], "known_src": [1, 2]}
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    except FileNotFoundError:
        pass
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
    session = "session-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".jsonl"
    writer = JsonlWriter(DATA_DIR / session)
    writer.start()

    stats = LinkStats()
    registry = ObserverRegistry()
    core = IngestCore(writer.sink, stats, registry,
                      allowed_sys=cfg["allowed_sys"], known_src=cfg["known_src"])

    writer.sink(to_jsonl(event_record(now_iso(), "service_start", session=session, config=cfg)))
    print(f"[ingest] {DATA_DIR / session}  allowed_sys={cfg['allowed_sys']} known_src={cfg['known_src']}", flush=True)

    transport = SpidevLgpioTransport()
    rx = SX127xRx(transport, LoRaConfig())
    rx.configure()

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    try:
        while not stop.is_set():
            frame = rx.receive()
            if frame:
                core.handle(frame.rssi_dbm, frame.payload, now_iso())
            else:
                time.sleep(0.02)
    finally:
        writer.sink(to_jsonl(event_record(
            now_iso(), "service_stop",
            decoded=core.decoded, errors=core.errors, foreign=core.foreign,
            anomalies={f"{k[0]}:{k[1]}": v for k, v in core.anomalies.items()})))
        writer.shutdown()
        transport.close()
        print("[ingest] stopped", flush=True)


if __name__ == "__main__":
    main()
