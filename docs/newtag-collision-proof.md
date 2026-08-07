# Collision proof — the ten additive tags vs. every special-cased name in the ground pipeline

**Scope of claim:** branch `feat/ground-newtags`, base `main` @ `0ca46dc`. Valid for the
pipeline as of that commit; a later special-case addition must re-run the census (§1 gives
the greps). The executable half of this proof is
`ground/flights/tests/test_newtag_collision_proof.py` — each verdict below that a test can
pin, a test pins.

**The ten tags** (2026-08-08 session decision "Packet decision: E+F", pending ADR 0001
Appendix-A/normative rows): `Vel Gmx Gmn Wmx Gyx Gyy Gyz Mgx Mgy Mgz`. All decode as
unitless floats — the spec rows live in `_V1_TAGS`, `ground/decode/v1.py`.

**Verdict up front: NO COLLISIONS.** Every name-match in the pipeline is an exact
whole-key comparison; no site matches tag names by prefix or substring. Two findings that
are not collisions are recorded in §4.

## 1. The census — every site that special-cases a tag NAME or frame KIND

Method: `grep -rn` across `ground/` (excluding tests) for (a) every literal tag-name
string, (b) frame-kind discriminators (`is_telemetry`, `max_is_meaningful`, beacon
handling), (c) all prefix/substring matching (`startswith`, `endswith`, `in` on keys).
`handheld/` contains no code yet (one ADR, no parser) — nothing to collide with there.

| # | Site | What it special-cases | Match mechanism |
|---|---|---|---|
| D1 | `ground/decode/v1.py:93` | `V` must be the first tag | exact `vkey != "V"` whole-string compare |
| D2 | `ground/decode/v1.py:110` | known-tag table | exact `dict.get(key)` — full key, no prefix |
| D3 | `ground/decode/v1.py:115` | unit-suffix stripping (`ft`/`C`/`V`) | applies only via the tag's OWN spec row after the D2 exact lookup; all ten new rows carry suffix `None` |
| I1 | `ground/ingest/core.py:59-60` | `SYS` allowlist, `SRC` known-set | exact `fields.get("SYS"/"SRC")` |
| I2 | `ground/ingest/core.py:61,82-88` | `CALL` Part-97 audit + binding mismatch | exact `unknown.get("CALL")` — reads the *unknown* dict, which the ten tags no longer inhabit |
| I3 | `ground/ingest/core.py:78` | `SEQ` feeds LinkStats | exact `"SEQ" in fields` |
| R1 | `ground/sessionlog/records.py:31-33` | `sys`/`src`/`seq` lifted onto the record | exact `fields.get(...)` |
| S1 | `ground/flights/segmenter.py:70` (`is_telemetry`) | beacon vs telemetry | presence of `St` ONLY — callers pass `fields.get("St")`, exact |
| S2 | `ground/flights/segmenter.py:42` (`max_is_meaningful`) | when `Max` is trustworthy | `St` value only |
| S3 | `ground/flights/segmenter.py:98,182-185` | peak (`ALT`/`Max`), loss (`SEQ`) | values arrive as parameters; both call sites (L1, V1 below) fetch by exact key |
| L1 | `ground/flights/live.py:38-40` | `SRC St ALT SEQ Max` into the segmenter | exact `fields.get(...)` |
| V1 | `ground/flights/derive.py:68-70` | same, offline rebuild | exact `fields.get(...)` |
| E1 | `ground/flights/export.py:13,38-39` | export columns | fixed 11-name list `_FIELD_TAGS`, exact lookups (see finding F1) |
| P1 | `ground/publish/data.py` | — | reads `Flight.stats` keys only; no wire-tag names |
| M1 | `ground/dashboard/model.py:64-70,97,100` | `SRC ALT St Max SEQ MET` + `CALL` | exact `fields.get(...)`; `CALL` from `unknown` (see I2) |
| K1 | `ground/linkstats/linkstats.py` | — | takes `(sys, src, seq)` as parameters; no name matching |
| O1 | `ground/oled/spec.py`, `ground/dashboard/templates/index.html` | — | consume the view model's keys, never wire tags |

Prefix/substring audit: the only `startswith`/`endswith` hits outside tests are
`ground/flights/flights.py:46` (flight-ID prefix, not a tag), `ground/decode/v1.py:115`
(VALUE suffix, gated by D2/D3), and two PiSugar/RTC line parsers
(`ground/panel/run_panel.py:58`, `ground/clock/rtc_restore.py:37`) that never see packet
text. **No tag NAME is matched by prefix or substring anywhere.**

## 2. Site × tag — why no new name can trigger any site

Because every mechanism in §1 is an exact whole-key match, the whole table reduces to one
question per pair: *is the new name string-equal to a special-cased name?* None is:

| New tag | vs `V` (D1) | vs known table (D2/D3) | vs `CALL` (I2) | vs `SYS SRC SEQ St ALT Max G Pg T Batt MET` (I1,I3,R1,S1-S3,L1,V1,E1,M1) |
|---|---|---|---|---|
| `Vel` | `"Vel" != "V"` — whole-string; pinned by `test_vel_never_matches_v` and `test_vel_as_first_token_is_not_a_version` | own row; no suffix | ≠ | ≠ all (nearest: `V` — see left) |
| `Gmx` | ≠ | own row | ≠ | ≠ all (nearest: `G`, `Max` — distinct keys; pinned by `test_similar_names_decode_independently`) |
| `Gmn` | ≠ | own row | ≠ | ≠ all (nearest: `G`; note `Grn` similarity, §4 F2) |
| `Wmx` | ≠ | own row | ≠ | ≠ all (nearest: `Max` — no shared key) |
| `Gyx` `Gyy` `Gyz` | ≠ | own rows | ≠ | ≠ all (no existing `Gy*` name) |
| `Mgx` `Mgy` `Mgz` | ≠ | own rows | ≠ | ≠ all (nearest: `Max`, `MET` — distinct keys; `Mgx` pinned in `test_similar_names_decode_independently`) |

Cross-cutting properties, each pinned by a test in
`ground/flights/tests/test_newtag_collision_proof.py`:

- **Frame KIND is decided by `St` alone.** A frame carrying all ten tags but no `St` is
  still a beacon (`test_stless_frame_with_all_new_tags_is_still_a_beacon`); a `St:0`
  PAD-shape frame is telemetry (`test_st_frame_with_all_new_tags_is_telemetry`).
- **Ingest counters stay flat** on a frame with all ten tags — `errors`, `foreign`,
  `anomalies`, `id_mismatches` all unmoved, frame fully ACCEPTED and dispatched, `SEQ`
  still counted (`test_frame_with_all_new_tags_is_fully_accepted`). Anti-hollow: the same
  frame shape on a foreign SYS *does* move `foreign`
  (`test_guards_can_fire_anti_hollow`), and a mismatched `CALL` beside the ten tags
  *does* move `id_mismatches` (`test_call_binding_still_works_beside_new_tags`) — the
  asserted-flat counters are live.
- **Peak accounting cannot ingest an envelope value.** `Gmx:199.9` / `Wmx:2293.8` never
  reach `peak_alt`; the peak still comes from `ALT`/`Max`, and SEQ-loss accounting is
  unchanged (`test_max_gate_reads_only_st_and_max`).
- **The dashboard panel is byte-identical** with and without the ten tags
  (`test_snapshot_identical_with_and_without_new_tags`).

## 3. ADR 0001 Appendix A naming rules

| Rule | Check |
|---|---|
| The 12 v1 names are reserved; no reuse | None of the ten equals any of `V SYS SRC SEQ St ALT Max G Pg T Batt MET` (string equality, the only relation the decoder has). |
| Prefer multi-character names | All ten are 3 characters. |
| `G` is G-force, never reused | `G` untouched. `Gmx`/`Gmn` are new names for a G-force-derived quantity (window envelope) — consistent with the rule's intent, not a reuse. |
| `Roll`/`Spin` reserved for 5.3 FUSION outputs | The raw 9-DoF channels deliberately do NOT take those names — `Gyx/Gyy/Gyz` (rate) and `Mgx/Mgy/Mgz` (field) are raw channels; `Roll`/`Spin` remain free for the fusion epic. No squatting. |
| Values contain no space/colon | Worst forms are plain signed decimals (`-2293.8` etc.) — clean. |

Tag-name matching is **case-sensitive** everywhere (Python `str` equality); no site
case-folds, so e.g. `Gmx` vs `G` cannot converge under normalization.

## 4. Findings (not collisions — reported, not fixed; both outside this branch's file set)

- **F1 — new tags are silently absent from the per-flight CSV export.**
  `ground/flights/export.py:13` fixes the column set as the 11 v1 tags, so `Vel`, the
  envelope and the 9-DoF channels will decode, log and derive fine but never appear in
  the published CSV trace — the very columns the OpenRocket-style plot (ADR 0005 §4)
  needs. Not a collision and not touched here (`export.py` is outside this stream's
  allowed files), but it must be extended before the plot epic consumes exports, or
  `Vel` ships to the ground and evaporates at the last hop.
- **F2 — visual near-miss, `Gmn` vs reserved `Grn`.** ADR 0001 Appendix A reserves `Grn`
  (APDS9960 green channel, `SRC:2`). `Gmn` ≠ `Grn` to every parser, but one glyph apart
  to every human reading a log. No action required; recorded so the lander epic picks
  `Grn` knowing its neighbor exists.
- **F3 — handheld has no parser yet** (`handheld/` is one ADR, no code), so the 8.x
  consumer inherits these names with no migration burden — worth citing this proof from
  the handheld parser's first commit.
