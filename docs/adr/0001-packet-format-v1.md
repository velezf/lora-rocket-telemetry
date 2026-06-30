# ADR 0001 — Packet Format v1 (shared telemetry contract)

Status: Accepted
Date: 2026-06-30
Deciders: Francisco Velez (KC3ZTQ)

## Context

The telemetry payload string is the wire interface between the rocket sled TX
(the only C++ node) and EVERY receiver: the Pi 5 ground station and the kids'
Pi Zero handheld today, and the lander (`SRC:2`) and future nodes later. It must
survive being independently encoded in C++ on the sled and decoded in Python on
the ground (decoder, Epic 4.1) — two implementations that can only stay in
agreement against a single written spec.

V1's string was ad hoc: unversioned, mixing keyed fields with bare emoji and a
space-bearing `[Charge Now]` status, formatted inline in one `snprintf`. It was
fragile to parse and impossible to evolve safely — a receiver had no way to know
which grammar it was looking at, and any field change silently broke decoders.

We need a formalized, versioned contract: one documented source of truth that the
C encoder and the Python decoder both implement, that can carry different field
sets from different vehicles, and that can grow without breaking deployed
receivers.

The encode/decode boundary is locked as **delimited ASCII with a leading version
field** (ASCII-vs-binary is not reopened here): serial-monitor-debuggable,
trivially symmetric to encode and decode, and transport-agnostic because
addressing rides inside the payload.

## Decision

A v1 packet is **space-delimited ASCII tokens**, each a **`KEY:VALUE` pair**, the
first token always **`V:1`**. Fields are **keyed, not positional** — a decoder keys
on tag name, ignores tags it does not recognize, and tolerates absent tags. Values
contain neither space nor colon. The decoder relies on the LoRa PHY-layer CRC for
integrity; there is no application-layer checksum in v1.

### v1 field spec

| Tag  | Order | Type   | Units        | Range / notes                                | Example      |
|------|-------|--------|--------------|----------------------------------------------|--------------|
| V    | 1     | int    | —            | format version; MUST be 1                    | `V:1`        |
| SYS  | 2     | uint8  | —            | network id (0–255); default 7                | `SYS:7`      |
| SRC  | 3     | uint8  | —            | source vehicle: 1=sled, 2=lander             | `SRC:1`      |
| SEQ  | 4     | uint16 | —            | per-TX counter, wraps at 65535               | `SEQ:42`     |
| St   | 5     | uint8  | —            | flight state: 0 pad / 1 ascent / 2 descent   | `St:1`       |
| ALT  | 6     | int    | feet         | barometric, may be negative                  | `ALT:1234ft` |
| Max  | 7     | int    | feet         | running max altitude                         | `Max:5678ft` |
| G    | 8     | float  | g (0.1)      | total accel magnitude                        | `G:2.3`      |
| Pg   | 9     | float  | g (0.1)      | peak G                                        | `Pg:9.1`     |
| T    | 10    | float  | °C (0.1)     | may be negative (`T:-5.0C`)                   | `T:21.5C`    |
| Batt | 11    | float  | volts (0.01) | raw cell voltage; status derived on ground   | `Batt:3.92V` |
| MET  | 12    | int    | seconds      | mission elapsed time since launch (0 on pad) | `MET:12`     |

Order is the encoder's canonical emission order, NOT a decode requirement. Per-tag
unit suffixes (`ft`/`C`/`V`) are fixed by this table; decoders strip the known
suffix for the tag.

### Canonical example packet (golden vector)

    V:1 SYS:7 SRC:1 SEQ:42 St:1 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V MET:12

~88 bytes; well under `RH_RF95_MAX_MESSAGE_LEN` (251). The C encoder (3.2) and the
Python decoder (4.1) both assert against this exact string.

## Integrity

Integrity is delegated to the **LoRa PHY-layer CRC**: corrupted frames are dropped
by the radio before they reach the decoder, so v1 carries **no application-layer
checksum**. A checksum tag (e.g. `CRC:…`) MAY be added additively later with **no
version bump** — itself a demonstration of the keyed, additive model below.

> **Bring-up check (Epic 2.5):** verify payload CRC is enabled on BOTH ends — the
> RadioHead TX (`RH_RF95`) and the `adafruit_rfm9x` RX — at radio bring-up.
> Mismatched CRC settings cause silent drops (one end emits/expects a CRC the other
> does not), which presents as total link loss with no error.

## Versioning & evolution

- **V semantics:** `V` is an integer naming the *grammar and the meaning of existing
  tags*. A decoder MUST read `V` first.
- **Unknown/mismatched version:** if `V` is a version the decoder does not implement,
  it MUST **reject the packet and surface it** (log / flag / loss-count). It MUST NOT
  best-effort parse a foreign version.
- **Additive tags are allowed WITHIN a version, without a bump.** New tags (e.g.
  `Roll`, `Spin` in Epic 5.3; the lander's BME680/APDS9960 tags in 7.3) may appear at
  any time. Decoders **tolerate unknown tags** — skip them, optionally surface them —
  and **tolerate absent tags** (the lander emits a different subset than the sled; a
  missing tag is valid, not an error).
- **The version bumps (→ `V:2`) if and only if** an *existing* tag changes in a way
  that would break a v1 decoder: a tag is renamed or removed, its units / precision /
  semantics change, its value type changes, or the grammar itself changes (delimiter,
  `KEY:VALUE` syntax, encoding). Adding a tag, reordering tags, or adding a new `St` /
  `SRC` *value* does NOT bump.
- **Errors vs. evolution:** only a malformed token (no colon, non-parseable value) or a
  wrong / unknown `V` is an error. Unknown tags and missing optional tags are normal.
- **Lockstep mechanism:** this table is the single source of truth. The C encoder (3.2)
  and the Python decoder (4.1) each ship unit tests that assert against the **golden
  example packet above**. Any change to the contract is a PR that edits this ADR (and
  bumps `V` per the rule above) before either implementation changes.

## Consequences

**Accepted tradeoffs**

- Slightly more airtime than a packed-binary format (~88 vs. ~25 bytes) — negligible at
  1 Hz / 251-byte LoRa frames.
- Values must avoid space and colon (this drove battery *status* to the ground side).

**Gains**

- Serial-monitor- and log-debuggable; symmetric, trivial encode/decode.
- Graceful evolution: additive tags + tolerant decoders mean new sensors and new
  vehicles ship without breaking deployed receivers; only genuine breaking changes bump.
- Heterogeneous nodes (sled, lander, handheld) share one grammar.

## Downstream dependents

The 3.2 C encoder, the 4.1 Python decoder, 4.3 logging / loss stats (`SEQ`, `SRC`),
4.4 / 4.6 dashboard + OLED, the 8.x handheld parser, and the Epic 7 lander — all
implement this table.

## Appendix A — Reserved & anticipated tags (non-normative)

This appendix reserves tag **names** ahead of the epics that will define them, to
prevent cross-node collisions. It is **non-normative**: units, precision, and exact
semantics are deliberately left TBD and become normative rows in the v1 field-spec
table when their epic lands — each an **additive, no-bump change** per the versioning
policy above. Reserving names now costs nothing and forecloses the one change that
*would* force a version bump: a name clash.

### Naming rules

- **The 12 v1 tags above are reserved globally** (`V SYS SRC SEQ St ALT Max G Pg T
  Batt MET`). No new tag may reuse one of these names for a different meaning.
- **Shared physical quantities reuse the existing tag, disambiguated by `SRC`.** The
  lander's temperature and battery are just `T` and `Batt` on `SRC:2` — same tags as
  the sled on `SRC:1`. Do not mint a second name for the same quantity.
- **`G` is G-force.** It must NOT be reused — in particular the APDS9960 green channel
  is **not** `G` (it is `Grn`, below). This is the concrete collision this appendix
  exists to prevent.
- **Prefer multi-character names for new quantities.** Single letters collide easily;
  the v1 set already spent most of them.

### Anticipated tags

| Candidate | Epic | SRC | Quantity | Units (TBD) | Notes |
|-----------|------|-----|----------|-------------|-------|
| `Roll` | 5.3 | 1 | roll rate | deg/s? | from 9-DoF fusion (LSM6DSOX/LIS3MDL); plan's example name |
| `Spin` | 5.3 | 1 | angle off vertical | deg? | plan's example name; maps to 5.2 "angle-off-vertical" — name/semantics to finalize in 5.3 |
| `T` | 7.3 | 2 | lander temperature | °C | **reuse** of v1 `T`, disambiguated by `SRC:2` (BME680) |
| `RH` | 7.3 | 2 | relative humidity | % | BME680 |
| `P` | 7.3 | 2 | barometric pressure | hPa? | BME680; lander may send raw pressure where the sled sends derived `ALT` |
| `Gas` | 7.3 | 2 | VOC / gas resistance | Ω or index? | BME680; raw-Ω vs. IAQ-index TBD |
| `Lux` | 7.3 | 2 | ambient light | lux / clear-count? | APDS9960 |
| `Rd` `Grn` `Blu` | 7.3 | 2 | color channels | counts? | APDS9960; **`Grn`, never `G`** |
| `Batt` | 7.3 | 2 | lander battery | V | **reuse** of v1 `Batt`, disambiguated by `SRC:2` |

Candidate names are front-runners, not commitments; the owning epic finalizes the
name, units, and precision when it adds the normative row. The reservations that ARE
firm are the *rules* above — especially that `G`, and every other v1 tag, is taken.
