"""ADR-0001 v1 telemetry packet decoder.

Pure function: validated payload bytes (from the ground RX driver, RadioHead
header already stripped) -> DecodedPacket | DecodeError. No radio imports, no
I/O — host-testable, runs identically on Mac and Pi.

Contract (see docs/adr/0001-packet-format-v1.md):
- Space-delimited ASCII `KEY:VALUE` tokens; first token must be `V:1`.
- Known tags are typed and unit-suffixes stripped; unknown tags are tolerated
  and surfaced raw (additive-extension policy); missing tags are valid.
- Any malformed/empty/truncated/wrong-version input returns a structured
  DecodeError. decode() never raises through to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass

# tag -> (kind, unit-suffix). V is handled specially (drives `version`).
_V1_TAGS = {
    "SYS": ("int", None),
    "SRC": ("int", None),
    "SEQ": ("int", None),
    "St": ("int", None),
    "ALT": ("int", "ft"),
    "Max": ("int", "ft"),
    "G": ("float", None),
    "Pg": ("float", None),
    "T": ("float", "C"),
    "Batt": ("float", "V"),
    "MET": ("int", None),
}


@dataclass
class DecodedPacket:
    version: int
    fields: dict      # known tag -> typed value (int/float); V excluded (see `version`)
    unknown: dict     # unrecognized tag -> raw str value
    raw: str
    ok = True


@dataclass
class DecodeError:
    reason: str       # empty | not-ascii | no-version | unsupported-version | malformed-token | bad-value
    detail: str
    raw: str
    ok = False


def _split_kv(tok: str, raw: str):
    """(key, value) or a DecodeError for a single KEY:VALUE token."""
    if tok.count(":") != 1:
        return DecodeError("malformed-token", f"token {tok!r} is not a single KEY:VALUE", raw)
    key, val = tok.split(":", 1)
    if not key or not val:
        return DecodeError("malformed-token", f"token {tok!r} has an empty key or value", raw)
    return key, val


def decode(payload) -> "DecodedPacket | DecodeError":
    if isinstance(payload, (bytes, bytearray)):
        try:
            raw = bytes(payload).decode("ascii")
        except UnicodeDecodeError:
            return DecodeError("not-ascii", "payload is not ASCII", repr(bytes(payload)))
    else:
        raw = str(payload)

    tokens = raw.split()
    if not tokens:
        return DecodeError("empty", "no tokens in payload", raw)

    # --- version first: a decoder MUST read V before anything else ---
    kv = _split_kv(tokens[0], raw)
    if isinstance(kv, DecodeError):
        return kv
    vkey, vval = kv
    if vkey != "V":
        return DecodeError("no-version", f"first tag is {vkey!r}, expected V", raw)
    try:
        version = int(vval)
    except ValueError:
        return DecodeError("bad-value", f"V value {vval!r} is not an int", raw)
    if version != 1:
        return DecodeError("unsupported-version", f"version {version} is not supported", raw)

    # --- remaining tags ---
    fields: dict = {}
    unknown: dict = {}
    for tok in tokens[1:]:
        kv = _split_kv(tok, raw)
        if isinstance(kv, DecodeError):
            return kv
        key, val = kv
        spec = _V1_TAGS.get(key)
        if spec is None:
            unknown[key] = val            # additive-extension policy: tolerate + surface
            continue
        kind, suffix = spec
        num = val[: -len(suffix)] if suffix and val.endswith(suffix) else val
        try:
            fields[key] = int(num) if kind == "int" else float(num)
        except ValueError:
            return DecodeError("bad-value", f"{key} value {val!r} is not a {kind}", raw)

    return DecodedPacket(version=version, fields=fields, unknown=unknown, raw=raw)
