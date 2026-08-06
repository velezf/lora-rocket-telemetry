# scratch — agent-adxl (Increment 2: per-axis accel as additive v1 tags)

**BASE COMMIT: `ca99691`** ("docs: Epic 6 handoff — one deployment event, Phase 0 ordered b->c->a").
Branch: `worktree-agent-a7e6e458b1b6637a5`. **UNFLASHED. Not merged, not pushed.**

---

## 1. THE GATE: unknown tags are INERT on the ground side — VERIFIED, PASSED

**An unknown tag increments NO error, anomaly, or foreign counter.** Proceeding was correct.

Traced by reading, then pinned by test:

- `ground/decode/v1.py` — `_V1_TAGS` lookup miss puts the tag in `unknown` and `continue`s.
  Only a malformed token, a bad value for a *known* tag, or a wrong `V` returns `DecodeError`.
- `ground/ingest/core.py` — `self.errors` increments only when `decode()` returns a non-`DecodedPacket`.
  `foreign` keys on `SYS`, `anomalies` on `SRC`. Neither reads the `unknown` dict.
- `ground/sessionlog/records.py` — `packet_record` carries `unknown` through verbatim,
  so the axis values land in the session JSONL for free.

Tests added in `ground/ingest/tests/test_ingest.py`, class
`TestAdditiveTagsDoNotPolluteLinkQuality` (5 tests, real decode + ingest path, no stubs):

| test | asserts |
|---|---|
| `test_additive_axis_tags_touch_no_counter` | `(errors, anomalies, foreign)` unchanged AND all zero |
| `test_additive_axis_tags_still_a_fully_accepted_packet` | guards the hollow pass — counters would also stay flat if the frame were *dropped*; it must be `decoded`, in stats, dispatched |
| `test_axis_values_land_in_unknown_and_reach_the_session_log` | `unknown == {"Ax":"-1.2","Ay":"0.4","Az":"9.7"}`, raw verbatim, v1 fields untouched |
| `test_counters_stay_flat_across_a_stream_of_tagged_frames` | 10 consecutive tagged frames, still `(0,{},{})` |
| `test_the_gate_can_actually_fail` | **"could this have failed?"** — a foreign `SYS` on the same frame DOES move a counter, so flat counters are an observation, not a tautology |

**One nuance worth knowing:** `CALL` is an unknown tag that ingest *does* read
(`core.py` pulls `d.unknown.get("CALL")` for the Part-97 ID audit trail, and it can move
`id_mismatches`). So "unknown ⇒ inert" is true for `Ax/Ay/Az` but is **not** a general
invariant of the unknown path — one tag name is already special-cased. Any future additive
tag should check it isn't shadowing a name ingest interprets.

## 2. Tags chosen: `Ax` `Ay` `Az`

Nothing in ADR-0001 Appendix A fits — `Roll`/`Spin` are 9-DoF *derived* quantities for
Epic 5.3, not raw per-axis acceleration. So these are invented, against the appendix rules:

- Not one of the 12 globally-reserved v1 names, and not an Appendix A candidate — no clash.
- **Multi-character**, as the appendix requires ("single letters collide easily").
- `G` is untouched and still the magnitude — the appendix's one explicit collision worry.
- Short, for airtime: 3 tags cost 22 bytes typical / 30 worst case.
- Units **g, signed, 1 decimal** — same precision and same gravity constant as `G`, so the
  axes and the magnitude are consistent by construction (there's a test for exactly that).

**If these get promoted to normative rows in the ADR table, that is an additive no-bump
change.** The wire format stayed v1; no `V` bump was needed or made.

## 3. HEADROOM — and a real defect found: `char msg[128]` was too small

Measured, encoder-exact:

| frame | bytes |
|---|---|
| ADR golden vector (before) | **88** |
| golden + `Ax/Ay/Az` (after, typical) | **110** |
| absolute worst case (all fields saturated, ADXL375 clipping ±200 g on all 3 axes) | **143** |

`main.cpp` used `char msg[128]`. **143 > 127, so the worst case would have TRUNCATED** —
bounded, never an overflow (`encode_packet` is `snprintf`-based and returns bytes actually
written), but a truncated frame silently loses its trailing tags.

Fix: `PACKET_BUF_LEN = 160` declared **once** in `firmware/lib/packet/packet.h`; `main.cpp`
now says `char msg[PACKET_BUF_LEN]` instead of repeating a literal ("cite, don't restate").
160 gives **17 bytes of headroom** over the worst case and is far under
`RH_RF95_MAX_MESSAGE_LEN` (251). Costs 32 bytes of *stack*, not static RAM.

Pinned by `test_worst_case_would_truncate_in_the_old_128_buffer`, which fails if anyone
shrinks the buffer back.

## 4. Libraries — verified, nothing added, nothing undeclared

`firmware/platformio.ini` **already declared everything this change needs**, version-pinned:
`adafruit/Adafruit ADXL375@1.1.2` and `adafruit/Adafruit Unified Sensor@1.1.15`.
Confirmed by resolution, not by eyeball — `pio pkg list -e feather_m0_tx` shows
ADXL375 1.1.2 → ADXL343 1.6.4 → BusIO 1.17.4 + Unified Sensor 1.1.15.

**I added no `lib_deps` entries, because none were needed** — the new conversion is pure C++
in `lib/convert`, and `e.acceleration.{x,y,z}` comes from the already-declared
`sensors_event_t`. This increment does not repeat the undeclared-library integrity problem.

## 5. Results

- `pio test -e native` — **29 passed** (18 at base + 8 packet/headroom + 3 convert).
- `pio run -e feather_m0_tx` — **SUCCESS**. RAM 17.5% (5736/32768, **unchanged**);
  Flash 21.4% (56052/262144), **+184 bytes** vs. the 55868-byte baseline (measured by
  stashing and rebuilding).
- `pytest ground/ -q` — **329 passed**, 6 subtests (324 at base + 5 gate tests).

---

## PICKUP NOTES — read before flashing

**BLIND SPOT / MERGE HAZARD (rule 8).** The task briefed me on two firmware commits said to
be in my base: a profile harness (`lib/profile`), a confirmed apogee detector
(`lib/apogee/apogee_confirm.h`), and a `main.cpp` restructured to sample at 20 Hz while
transmitting at 1 Hz. **None of that is in `ca99691`** — no `lib/profile`, no
`apogee_confirm.h`, and `main.cpp` is the single-tick `delay(1000)` version. The native
baseline here was **18 tests, not the 26** the brief cited. Those commits live on a branch
invisible to my base. Consequences:

- **`firmware/src/main.cpp` WILL CONFLICT with the restructure.** My change there is 5 lines
  and trivially re-appliable — see below.
- **Everything else should merge clean.** `lib/packet`, `lib/convert`, their tests, and the
  ground test are untouched by the restructure as described.

**Re-applying the `main.cpp` hunk onto the restructured loop** — at the SAMPLE tick, where
`adxl.getEvent(&e)` already runs, the `sensors_event_t e` is in scope:

```cpp
p.has_axes = true;
p.ax = accel_axis_g(e.acceleration.x);
p.ay = accel_axis_g(e.acceleration.y);
p.az = accel_axis_g(e.acceleration.z);
```

plus `char msg[PACKET_BUF_LEN];` in place of `char msg[128];`.

**Sampling-rate question the restructure raises and I could not answer from my base:** with
20 Hz sampling and 1 Hz TX, the axes I set are whatever the *most recent* sample held — a
1-in-20 snapshot, not the interesting one. `G`/`Pg` already carry a running peak. If the
point of per-axis data is to catch a hard lateral hit, **the transmitted axes should
probably be the axes AT the peak-magnitude sample of that 1 s window**, not the last one.
That is a design decision for whoever owns the restructured loop; the encoder supports
either without change.

**Trigger to revive:** if increment 1 benches clean and there is time before the launch
window. Otherwise this parks as-is — it is self-contained and the gate result above stands
on its own regardless of whether the firmware ever flashes.
