# Telemetry Dictionary — v1 packet prefixes

Quick reference for the `KEY:VALUE` prefixes in the LoRa telemetry stream, so you
don't have to decode a packet by memory. **Authoritative source:
[ADR 0001](adr/0001-packet-format-v1.md)** — this page is a friendly index; if the
two ever disagree, the ADR wins.

A packet is space-delimited ASCII tokens, each a `KEY:VALUE` pair, always starting
with `V:1`. Decoders key on the tag name, **ignore tags they don't recognize**, and
tolerate missing ones. Example:

```
V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12
```

## v1 tags (currently emitted by the sled)

| Prefix | Meaning | Units / format | Example | Notes |
|--------|---------|----------------|---------|-------|
| `V`    | format version | int | `V:1` | always first; MUST be `1` for v1 |
| `SYS`  | network id | 0–255 | `SYS:7` | default `7`; filters cross-network traffic |
| `SRC`  | source vehicle | code | `SRC:1` | `1` = sled, `2` = lander |
| `SEQ`  | packet counter | 0–65535 | `SEQ:42` | per-TX, wraps at 65535; drives loss stats |
| `St`   | flight state | code | `St:1` | `0` = pad, `1` = ascent, `2` = descent |
| `ALT`  | altitude | feet | `ALT:1234ft` | barometric; may be negative |
| `Max`  | max altitude | feet | `Max:5678ft` | running peak |
| `G`    | acceleration | g (1 decimal) | `G:2.3` | total magnitude |
| `Pg`   | peak G | g (1 decimal) | `Pg:9.1` | max G seen so far |
| `T`    | temperature | °C (1 decimal) | `T:21.5C` | may be negative (`T:-5.0C`) |
| `Batt` | battery | volts (2 decimals) | `Batt:3.92V` | raw cell voltage; status derived on the ground |
| `MET`  | mission elapsed time | seconds | `MET:12` | since launch; `0` on the pad |

### Code values
- **`SRC`** — `1` sled · `2` lander
- **`St`** — `0` pad · `1` ascent · `2` descent

## Reserved / not-yet-emitted tags

Reserved ahead of the epics that will define them so future sensors don't collide.
They may appear later **additively (no version bump)**; decoders already skip tags
they don't know. Names are front-runners, not commitments — see
[ADR 0001](adr/0001-packet-format-v1.md), Appendix A.

| Prefix | Planned meaning | Epic · source |
|--------|-----------------|---------------|
| `Roll` | roll rate | 5.3 · 9-DoF (sled) |
| `Spin` | angle off vertical | 5.3 · 9-DoF (sled) |
| `RH`   | relative humidity | 7.3 · lander BME680 |
| `P`    | barometric pressure | 7.3 · lander BME680 |
| `Gas`  | VOC / gas resistance | 7.3 · lander BME680 |
| `Lux`  | ambient light | 7.3 · lander APDS9960 |
| `Rd` `Grn` `Blu` | color channels | 7.3 · lander APDS9960 — **`Grn`, never `G`** |

Shared physical quantities **reuse the same tag, disambiguated by `SRC`** — the
lander's `T` and `Batt` are the same tags on `SRC:2`.

## Rules of thumb
- **Unknown tag?** Ignore it — the format is forward-compatible by design.
- **Missing tag?** Valid — the lander sends a different subset than the sled.
- **`G` is G-force**, never the green color channel (that's `Grn`).
- Only a wrong/unknown `V` or a malformed token (no colon) is an error.
