"""Flight index + ops CLI (offline; touches files only, never the radio).

    rebuild  <session.jsonl> [--ops ops.jsonl] [-o flights.json] [--silence 90]
    list     <flights.json>
    annotate <flight_id> --index <flights.json> --ops <ops.jsonl> [--label ..] [--motor ..] [--field ..]
    close    <flight_id> --index <flights.json> --ops <ops.jsonl> [--at <iso>]
    open     --src <n> --at <iso> --ops <ops.jsonl>
    export   <flights.json> <session.jsonl> <flight_id> [--format csv|json] [-o out]
    publish  [flight_id] --site <dir> (--local-session s.jsonl | --host u@pi --data <dir>) [--ops ops.jsonl]

Manual ops are appended to the ops journal; the index is only ever (re)written by
`rebuild` = derive(session, ops). One writer per file — no races.

`publish` mechanizes the Stage-1 data hop (the F1 one-off scp RESUME warned
about): fetch session+ops from the Pi into a local mirror (which doubles as the
off-SD backup of the ops journal — the system's only irreplaceable file), then
write the FULL flights.json + the flight's CSV into the site repo's data dir.
It STOPS there: reviewing the site-repo diff and committing/pushing stays human.
"""
import argparse
import json
import sys
from pathlib import Path

from ground.flights.flights import flights_to_json, flights_from_json
from ground.flights.derive import derive_flights
from ground.flights.export import flight_rows, rows_to_csv, rows_to_json
from ground.flights.publish import publish_flight


def _read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def _append_op(ops_path, record):
    with open(ops_path, "a") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def _find(index_path, flight_id):
    flights = flights_from_json(Path(index_path).read_text())
    f = next((x for x in flights if x.flight_id == flight_id), None)
    if f is None:
        sys.exit(f"no flight {flight_id} in {index_path}")
    return f


def cmd_rebuild(a):
    flights = derive_flights(_read_jsonl(a.session), ops=_read_jsonl(a.ops), silence_timeout_s=a.silence)
    Path(a.out).write_text(flights_to_json(flights))
    print(f"wrote {len(flights)} flight(s) to {a.out}")


def cmd_list(a):
    for f in flights_from_json(Path(a.index).read_text()):
        s = f.stats
        print(f"{f.flight_id}  SRC:{f.src}  {f.t_start} .. {f.t_end}  "
              f"peak={s.get('peak_alt_ft')}ft dur={s.get('duration_s')}s "
              # `rx` is TELEMETRY only and `beacons` is shown beside it, never
              # folded in — see ground/flights/segmenter.py is_telemetry.
              f"rx={s.get('packets_rx')} lost={s.get('packets_lost')} "
              f"beacons={s.get('beacons_rx', 0)}  {f.label}".rstrip())


def cmd_annotate(a):
    f = _find(a.index, a.flight_id)
    _append_op(a.ops, {"op": "annotate", "src": f.src, "at": f.t_start,
                       "label": a.label, "motor": a.motor, "field": a.field})
    print(f"journaled annotate for {a.flight_id} (SRC:{f.src} @ {f.t_start})")


def cmd_close(a):
    f = _find(a.index, a.flight_id)
    at = a.at or f.t_end
    _append_op(a.ops, {"op": "close", "src": f.src, "at": at})
    print(f"journaled close for {a.flight_id} (SRC:{f.src} @ {at})")


def cmd_open(a):
    _append_op(a.ops, {"op": "open", "src": a.src, "at": a.at})
    print(f"journaled open for SRC:{a.src} @ {a.at}")


def cmd_export(a):
    flight = _find(a.index, a.flight_id)
    rows = flight_rows(_read_jsonl(a.session), flight)
    out = rows_to_csv(rows) if a.format == "csv" else rows_to_json(rows)
    if a.out:
        Path(a.out).write_text(out)
        print(f"wrote {len(rows)} rows to {a.out}")
    else:
        print(out)


def cmd_publish(a):
    if a.local_session:
        session_path = Path(a.local_session)
    else:
        # Fetch from the Pi into the mirror. The mirror IS the ops-journal
        # backup: every publish refreshes the off-SD copy of the one file in
        # this system that cannot be re-derived.
        import subprocess
        mirror = Path(a.mirror).expanduser(); mirror.mkdir(parents=True, exist_ok=True)
        if a.session == "latest":
            ls = subprocess.run(
                ["ssh", a.host, f"ls -t {a.data}/session-*.jsonl | head -1"],
                capture_output=True, text=True, check=True)
            remote_session = ls.stdout.strip()
        else:
            remote_session = f"{a.data}/{a.session}"
        subprocess.run(["scp", "-q", f"{a.host}:{remote_session}", str(mirror)],
                       check=True)
        subprocess.run(["scp", "-q", f"{a.host}:{a.data}/ops-journal.jsonl", str(mirror)],
                       check=True)
        session_path = mirror / Path(remote_session).name
        a.ops = str(mirror / "ops-journal.jsonl")
        print(f"fetched {session_path.name} + ops-journal.jsonl -> {mirror} (off-SD backup)")

    site = Path(a.site).expanduser()
    if not site.is_dir():
        sys.exit(f"site data dir not found: {site}")
    flights = publish_flight(_read_jsonl(session_path), _read_jsonl(a.ops),
                             a.flight_id, site, silence_s=a.silence)
    picked = a.flight_id or flights[-1].flight_id
    print(f"published flights.json ({len(flights)} flight(s)) + {picked}.csv -> {site}")
    print("NOT committed: review the site repo diff, then commit/push it yourself.")


def build_parser():
    p = argparse.ArgumentParser(prog="flights")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rebuild"); r.add_argument("session")
    r.add_argument("--ops", default="ops-journal.jsonl"); r.add_argument("-o", "--out", default="flights.json")
    r.add_argument("--silence", type=float, default=90); r.set_defaults(func=cmd_rebuild)

    l = sub.add_parser("list"); l.add_argument("index"); l.set_defaults(func=cmd_list)

    an = sub.add_parser("annotate"); an.add_argument("flight_id")
    an.add_argument("--index", required=True); an.add_argument("--ops", required=True)
    an.add_argument("--label"); an.add_argument("--motor"); an.add_argument("--field")
    an.set_defaults(func=cmd_annotate)

    c = sub.add_parser("close"); c.add_argument("flight_id")
    c.add_argument("--index", required=True); c.add_argument("--ops", required=True); c.add_argument("--at")
    c.set_defaults(func=cmd_close)

    o = sub.add_parser("open"); o.add_argument("--src", type=int, required=True)
    o.add_argument("--at", required=True); o.add_argument("--ops", required=True); o.set_defaults(func=cmd_open)

    e = sub.add_parser("export"); e.add_argument("index"); e.add_argument("session"); e.add_argument("flight_id")
    e.add_argument("--format", choices=["csv", "json"], default="csv"); e.add_argument("-o", "--out")
    e.set_defaults(func=cmd_export)

    pub = sub.add_parser("publish"); pub.add_argument("flight_id", nargs="?", default=None)
    pub.add_argument("--site", default="~/velezf.github.io/projects/lora-flights")
    pub.add_argument("--local-session", default=None,
                     help="already-local session JSONL (skips the Pi fetch)")
    pub.add_argument("--host", default="rocketman@apogee-gs.local")
    pub.add_argument("--data", default="/home/rocketman/apogee-data")
    pub.add_argument("--mirror", default="~/apogee-data-mirror")
    pub.add_argument("--session", default="latest",
                     help="'latest' (by mtime on the Pi) or a session filename")
    pub.add_argument("--ops", default="ops-journal.jsonl")
    pub.add_argument("--silence", type=float, default=90)
    pub.set_defaults(func=cmd_publish)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
