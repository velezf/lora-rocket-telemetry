# ADR 0004 (DRAFT) — Frame-type classification before field interpretation

Status: **DRAFT — proposed amendment to [ADR 0001](0001-packet-format-v1.md). Not accepted. No code written.**
Date: 2026-08-02
Deciders: Francisco Velez (KC3ZTQ) — this draft exists for that decision, and makes a
recommendation at every fork rather than deciding silently.
Amends: [ADR 0001 — Packet Format v1](0001-packet-format-v1.md) (the locked wire contract)

> **Base commit — what this draft could and could not see.** Written against `6f8f5e9`
> (`main`), not the working branch. Two backlog items cited here — **C2** (the high-rate dump
> frame) and the **wire-level absent-vs-zero** question (§6) — exist on the working branch and
> were **not visible from this base**; they are cited from session context, and their exact
> wording should be checked against the branch before this ADR is accepted. Every claim about
> `ground/`, `firmware/` and ADR 0001 below was read directly at `6f8f5e9` and re-verified by
> execution where marked.

---

## 1. Context

ADR 0001 locks the wire format and grants receivers two tolerances that, together, are the
problem:

> Decoders **tolerate unknown tags** … and **tolerate absent tags** (the lander emits a
> different subset than the sled; a missing tag is valid, not an error).
> — [ADR 0001, "Versioning & evolution"](0001-packet-format-v1.md)

Those two rules were written for **sensor evolution** — a node that adds `Roll`, a lander that
omits `ALT`. They are silently also a licence for a **different kind of frame entirely**, and
nothing in the contract distinguishes the two cases. ADR 0001 has exactly one frame: telemetry.
Every receiver was built on that assumption without ever writing it down.

Three items already on the roadmap break the assumption:

| Source | Frame | Shape |
|---|---|---|
| **Epic 6 rider 4** — Part-97 station ID (`RESUME.md` → "Epic 6 firmware riders") | beacon | `V:1 SYS:7 SRC:1 CALL:KC3ZTQ` — **no `St`, no `ALT`, no `SEQ`** |
| **Epic 7** — lander (`SRC:2`), BME680/APDS9960 ([ADR 0001 App. A](0001-packet-format-v1.md#appendix-a--reserved--anticipated-tags-non-normative)) | atmosphere telemetry | may legitimately carry **no `ALT` at all** |
| **Backlog C2** — high-rate post-flight dump *(not visible from this base — see header)* | dump | telemetry-shaped, and **must not carry `SEQ`** (§7) |

To every consumer in `ground/` today, none of these is "a new frame type". Each is a
**syntactically valid v1 telemetry packet that happens to be missing fields**.

### 1.1 The concrete failure (re-verified 2026-08-02 by execution at `6f8f5e9`)

The main thread measured this; it was re-run here to locate it exactly, because the location
turns out to matter. A single beacon frame injected mid-flight into an F1-shaped stream:

| Path | `packets_lost` | `peak_alt_ft` | published peak AGL |
|---|---|---|---|
| **Live** (`LiveFlights` → `FlightSegmenter`) | **65,535** (true: 0) | **0** (true: −74) | **84 ft** (true: 10 ft) |
| **Canonical rebuild** (`derive_flights`) | 0 ✅ | −74 ✅ | 10 ft ✅ |

The mechanism is two coercions, in two files, that turn *absent* into *a number*:

- `ground/flights/live.py:38-39` — `f.get("ALT") if … is not None else 0` and the same for `SEQ`.
- `ground/flights/derive.py:62-63` — the identical pair.

With `SEQ` coerced to `0`, `FlightSegmenter.observe` computes
`gaps += (0 - last_seq - 1) % 65536` (`ground/flights/segmenter.py:84`) — 65,506 fabricated
losses on the beacon, plus 29 more when the next real packet "wraps" back. With `ALT` coerced
to `0`, `peak_alt = max(peak, 0)` (`segmenter.py:78`) replaces a true peak of −74 ft with 0,
and against F1's real `baseline_ft` of −84 that publishes **84 ft where the truth is 10 ft**.

The live/canonical split is itself a finding: the `flight_close` advisory event written into the
session log carries the *live* stats, and `flights-snapshot.json` likewise. Both would record
65,535 losses for a flight the canonical rebuild scores at 0. The
"index = pure f(session, ops)" promise holds; **the advisory record beside it lies.**

### 1.2 What is already correct (do not "fix" these)

- `LinkStats` is **not** corrupted by a beacon — verified: 0 gaps. It is guarded by
  `core.py:78` (census row C, below), and that guard is the pattern the rest should copy.
- `CALL` already rides the unknown-tag path into a Part-97 `id` audit event
  (`core.py:61,83`), and a beacon correctly advances `last_rx_ts`/`G_RX` — a beacon **is** real
  RX activity, and a station that IDs but stops sending telemetry is genuinely still alive.
- Every existing ground test models `CALL` as a **rider appended to the full golden telemetry
  frame** (`GOLDEN + b" CALL:KC3ZTQ"` — `ground/decode/tests/test_v1.py:68`,
  `ground/ingest/tests/test_ingest.py:144`). **The ground side has never been tested against a
  standalone beacon.** That is why this is undetected rather than fixed.

---

## 2. Census — the system already classifies frames, six times, by accident

**This is the core finding, and it reframes the whole amendment.** Draft-0004 does not
*introduce* frame-type classification. Classification is already happening, in at least six
places, each with its own private, unstated notion of what a telemetry frame is — **none of
them named, none of them agreeing, and one of them empty.**

Every row below was located by direct search at `6f8f5e9`.

| # | Site | Predicate | What it implicitly means by "telemetry" | What it silently does to a frame that fails | Under `FT` (§4) |
|---|---|---|---|---|---|
| **A** | `ground/flights/live.py:32-39` (`LiveFlights.on_observation`) | **none — no gate at all** | *"every decoded frame is telemetry"* | nothing fails; **everything** is fed to the segmenter, absent `ALT`/`SEQ` coerced to `0` | **REPLACED** — receives only `TELEMETRY` via typed fan-out; coercions deleted (§6) |
| **B** | `ground/flights/derive.py:45` (index derivation) | `type=="packet" and "fields" in r and fields.get("St") is not None` | *"telemetry is a frame that reports a flight state"* | **silently dropped from segmentation. No counter, no event, no log line.** | **REPLACED** by the shared `frame_type()` predicate — see §2.1 for the behaviour change |
| **C** | `ground/ingest/core.py:78` (LinkStats gate) | `if "SEQ" in f` | *"telemetry is a frame with a sequence number"* | skipped for loss accounting — **correct outcome, but silent and unnamed** | **KEPT**, demoted to belt-and-braces: under §7 no non-telemetry frame carries `SEQ`, and typed fan-out already excludes them |
| **D** | `ground/ingest/core.py:61,83` (Part-97 audit) | `d.unknown.get("CALL")` | the **inverse** classifier: *"a frame carrying `CALL` is an identification"* | no `id` event — but note it currently fires on **telemetry frames too**, since `CALL` is tested only as a rider | **RETAINED but re-sited**: must be reachable from the `ID` path, not only from the accepted-telemetry path |
| **E** | `ground/dashboard/model.py:57-59` (`LiveState.update`) | `src = f.get("SRC"); if src is None: return` | *"telemetry is a frame with a source id"* | **silently returns.** A beacon **has** `SRC`, so it passes and clobbers the panel: `alt`/`st`/`seq`/`met` → `None`, `None` appended to the trace and `alt_hist` | **REPLACED** — telemetry-only, except `CALL` capture (`model.py:61`) which must still see `ID` frames |
| **F** | `ground/flights/export.py:20` (per-flight CSV/JSON rows) | `type=="packet" and r.get("src")==flight.src` | *"telemetry is any packet record from this flight's source"* | excluded from the export — but a beacon **has** `src`, so it **passes** and emits a row with all 11 field columns `None`, **into the published per-flight CSV** | **REPLACED** — telemetry-only, or the row is emitted with an explicit type column |

**Adjacent, and the instructive contrast:** `core.py:63,70` gate on `SYS`/`SRC` policy
(`allowed_sys`, `known_src`). Those are not frame-type classifiers, but they are the same
*shape* of decision — and they get it right: a frame that fails is **counted** (`self.foreign`,
`self.anomalies`) **and** written as an advisory event (`foreign_sys`, `unknown_src`). Network
policy failures are surfaced; frame-shape failures are not. That asymmetry is the whole gap.

**Not classifiers, but where the consequence surfaces:** `ground/oled/spec.py:66` and
`ground/oled/render.py:8` render `"--"` for a `None` altitude, and `spec.py` renders `"?"` for
an unknown state. These are correct display fallbacks doing their job — they are the visible
symptom of row E, not a seventh definition.

### 2.1 Row B mis-fires forward, and the way it fails is the strongest argument here

`derive.py:45` uses "has `St`" as a proxy for "is telemetry". It happens to exclude a beacon,
which is why the canonical index survives §1.1. But the proxy is wrong in the other direction
too: **an Epic 7 lander frame (`SRC:2`) carrying BME680/APDS9960 atmosphere data but no `St`
would be silently dropped from flight derivation — no anomaly counted, no event written, no
log line, no error.** The flight would simply be shorter, or absent, and nothing in the system
would say why.

**This is the same failure class as `ObserverRegistry.dispatch` swallowing consumer exceptions**
(`ground/ingest/registry.py:22-24` — a bare `except Exception: pass`). Both are *deliberate,
correct-in-intent isolation* — the registry must not let a consumer crash the radio loop, and
derive must not let a malformed record break a rebuild — and both **discard the evidence that
the isolation fired.** A dead OLED consumer and a dropped lander frame look identical from
outside: everything runs, nothing errors, and the output is quietly incomplete.

The project has already named this pattern and rejected it once, in the panel LEDs: a
*designed-but-inert* safety signal is worse than an absent one, because the panel reads "fine"
while the condition goes unshown (`RESUME.md` → "Panel signals designed but INERT"). A silent
frame drop is the same bargain — the index reads "fine" while a node's data is being discarded.

**Consequence for this ADR:** whatever classification rule replaces the census, a frame that
fails it must be **counted and surfaced**, exactly as `foreign_sys` and `unknown_src` already
are. Classification without a counter just moves the silence.

### 2.2 What the amendment actually is

**Replacement, not addition.** The value of `FT` is not that it adds a capability the system
lacks — the system already classifies frames six times over. The value is that it **collapses
six accidental, undocumented, mutually-inconsistent definitions into one explicit rule, stated
in the contract, computed once, and shared by every consumer.**

That reframing changes what the amendment has to justify. It is not "should we take on a new
mechanism?" — the mechanism is already here, unowned. It is "should the definition of a
telemetry frame be *declared by the transmitter and written in ADR 0001*, or continue to be
*re-guessed independently by each consumer from whichever field it happens to need*?" Six
divergent guesses, one of them empty, is the status quo's answer.

The strongest evidence that the status quo cannot hold: **rows A and B are the same decision,
made in two places, and they disagree** — 65,535 fabricated losses versus 0, on identical
input. Nothing detected that for the entire development of Epic 4.

---

## 3. The `V`-bump question — answered honestly

**Verdict: NO version bump. This is an in-version, additive amendment to `V:1`.**

**The letter of the policy says no bump.** ADR 0001 bumps `V` "if and only if an *existing* tag
changes in a way that would break a v1 decoder: a tag is renamed or removed, its units /
precision / semantics change, its value type changes, or the grammar itself changes." Adding a
frame-type tag renames nothing, removes nothing, changes no unit or type, and does not touch
the `KEY:VALUE`/space grammar. The golden vector decodes byte-identically. The C encoder is not
modified at all.

**The honest objection.** A `V` is defined as naming "the grammar *and the meaning of existing
tags*", and this amendment does change something real: **what a conforming receiver must do**.
Before it, "read the tags you know, ignore the rest" was a complete receiver contract. After
it, a receiver must first ask *what kind of frame is this* and only then interpret fields. That
is a change in obligation, and pretending otherwise would be the claiming-coverage-we-lack
pattern.

**Why it is still not a bump.** The incompatibility this amendment describes **already exists
under ADR 0001 exactly as written**. ADR 0001 already declares that a missing tag is valid, so
`V:1 SYS:7 SRC:1 CALL:KC3ZTQ` is *already a conforming v1 packet today* — and today's receivers
already mishandle it six different ways (§2). This amendment does not create an incompatibility;
it **names a hazard the existing tolerance rule already permits and closes it**. A version bump
is the tool for "old decoders must stop parsing this"; here we want the opposite — old decoders
must keep parsing telemetry unchanged, and the fix is on the receiver side regardless.

**Rejected alternative — `V:2` for non-telemetry frames only.** Superficially attractive: ADR
0001 mandates that a decoder reject an unimplemented version and surface it, so a `V:2` beacon
would be *safely* rejected by every deployed v1 receiver rather than silently mis-parsed.
Rejected for three reasons:

1. It converts a data-corruption bug into an **alarm-fatigue bug**: every station ID (every
   ≤9.5 min, per Epic 6 rider 4) would land in `core.errors` and write an `error` packet record
   — a permanent stream of "errors" for correct, required behaviour.
2. **Part-97 station ID should be maximally receivable**, not deliberately rejected by the
   fleet. Making the one legally-required transmission the one nobody can decode is backwards.
3. It creates a **mixed-version stream from a single node**, which ADR 0001's "a decoder MUST
   read `V` first" model was never designed for, and which forecloses the far more likely
   future where `V:2` means a real grammar change.

**Amendment mechanics.** Per ADR 0001's lockstep rule, this lands as a PR editing ADR 0001
(adding one normative row and one new subsection) *before* either implementation changes.

---

## 4. Proposed mechanism

### 4.1 On the wire: one additive tag, `FT`

Add one row to the ADR 0001 v1 field-spec table:

| Tag | Order | Type | Units | Range / notes | Example |
|-----|-------|------|-------|---------------|---------|
| `FT` | 2 (after `V`) | uint8 | — | **frame type. ABSENT ⇒ `0` (telemetry).** | `FT:1` |

Frame-type registry (a new normative subsection of ADR 0001, extended additively like `St`
codes — [adding a new `St`/`SRC` value does not bump `V`](0001-packet-format-v1.md)):

| `FT` | Name | Meaning | Carries `SEQ`? |
|---|---|---|---|
| `0` | `TELEMETRY` | vehicle state sample; the only type that feeds flights, AGL, loss stats | **yes** |
| `1` | `ID` | Part-97 station identification beacon (Epic 6 rider 4) | **no** (§7) |
| `2` | `DUMP` | post-flight high-rate record replay (backlog C2) | **no** (§7) |

**Four rules make this work, and all four are load-bearing:**

1. **Absent ⇒ `FT:0`.** The existing sled emits no `FT` and is not modified; every frame it has
   ever sent, and every byte in the F1 golden fixture, classifies as telemetry with no change.
   This is what keeps the locked contract and the golden vector intact (§8).
2. **An unrecognized `FT` *value* is NOT telemetry.** This deliberately **inverts** ADR 0001's
   unknown-tag rule. Unknown *tag* → ignore and continue (evolution is additive and safe).
   Unknown *frame type* → do not interpret the frame's fields at all. Interpreting an unknown
   frame type as telemetry is precisely the failure in §1.1, so the fail-safe direction is
   "refuse to guess".
3. **A frame that fails classification is counted and surfaced**, never silently dropped — the
   `foreign_sys`/`unknown_src` pattern, per §2.1. This is what stops the amendment from
   re-creating row B's silence under a new name.
4. **`FT` declares type; it does not vouch for completeness.** A frame claiming `FT:0` but
   missing `ALT` is a *telemetry frame with an absent field*, and §6 governs it. Classification
   and completeness are separate checks and must not be collapsed.

**Fork — numeric vs symbolic values.** `FT:1` (recommended) matches every other v1 tag, all of
which take numeric values, and matches the `St` code precedent exactly; it costs 4 bytes.
`FT:ID` is self-describing on a serial monitor, which ADR 0001 names as an explicit design
value, at ~5-6 bytes. **Recommendation: numeric**, on consistency — a reader needs the registry
table for the semantics either way, and `St:1` already establishes that this project encodes
enumerations as small ints.

**Fork — should the sled start emitting an explicit `FT:0`?** **Recommendation: no.** It costs
4 bytes on every packet forever for information that `absent ⇒ 0` already conveys; it would
change the C golden vector and force `firmware/test/test_packet` and
`ground/decode/tests/test_v1.py::GOLDEN` to be rewritten; and it would make the F1 fixture's
frames differ in shape from current-firmware frames. The whole value of `absent ⇒ 0` is that
the fleet's existing emitter is already conforming.

### 4.2 On the ground: classify once, before interpreting

**Where.** A pure predicate beside the decoder — `ground/decode/` is the one module every
consumer already imports, and it is precisely the "before interpreting fields" boundary:

```
frame_type(decoded) -> FrameType     # pure, host-tested, no I/O
```

It reads `FT` when present. When absent it returns `TELEMETRY`, per rule 1. **This one function
is what all six census rows collapse into.**

**How consumers get it — two options, and this is the important fork.**

- **(a) Minimal — every consumer calls `frame_type()` itself.** ~6 call sites, no architectural
  change. *But it is the same shape as the census*: six sites each responsible for remembering,
  which is exactly how rows A and B came to disagree.
- **(b) Structural — the registry fans out by type** (recommended for the live path).
  `IngestCore` classifies once and dispatches `TELEMETRY` observations only to telemetry
  consumers; `ID` frames go to the Part-97 audit path (row D); unknown types are counted as an
  anomaly alongside `foreign_sys`/`unknown_src` (rule 3). A telemetry consumer then **cannot**
  receive a beacon, so it cannot forget.

**Recommendation: (b) for the live path (rows A, C, D, E), plus the shared pure predicate for
the two file-reading consumers** — `derive_flights` (row B) and `flight_rows` (row F) read the
session log rather than the registry, so they must apply the same rule at their own filters.
The shared predicate is what keeps registry-fed and file-fed paths equal.

**And a test that makes divergence impossible to reintroduce:** feed one record stream through
the live segmenter and through `derive_flights` and **assert the resulting stats are identical**.
That test fails today (65,535 vs 0). It is the acceptance test for this ADR, and it is the
direct answer to rows A-vs-B.

---

## 5. Consumer obligations

Census rows are cited by letter; §2's final column states the predicate change and is not
repeated here.

| Consumer | Must change? | What |
|---|---|---|
| `ground/decode/v1.py` | **Yes (small)** | Add `FT` to `_V1_TAGS` as an int and add the pure `frame_type()` predicate. `decode()` itself stays type-agnostic — it still decodes any frame; classification is a separate call. |
| `ground/ingest/core.py` | **Yes** | Rows **C** + **D**. Classify after the SYS/SRC policy gates and before fan-out; dispatch only `TELEMETRY` to telemetry observers. Count unknown-`FT` frames as an anomaly + advisory event (rule 3). Keep persisting **every** frame's raw (D1: history must stay re-decodable). Consider splitting the `decoded` counter so beacons are not counted as telemetry packets in the `service_stop` summary. |
| `ground/linkstats/linkstats.py` | **No** | Row **C** is already correct and is the model. **A non-telemetry frame must never consume a sequence number** (§7). |
| `ground/flights/live.py` + `segmenter.py` | **Yes — the corruption site** | Row **A**. `on_observation` must only receive `TELEMETRY`. Independently, the `else 0` coercions must go (§6). |
| `ground/flights/derive.py` | **Yes** | Row **B**. Replace the `St is not None` proxy with the shared predicate, drop the two `else 0` coercions, and **count what it excludes** (§2.1). |
| `ground/flights/export.py` | **Yes** | Row **F**. Today a beacon inside a flight's time span emits an all-`None` row **into the published per-flight CSV**. This is the only census row that reaches a public artifact. |
| `ground/dashboard/model.py` | **Yes** | Row **E**. `LiveState.update` must be telemetry-only. Beyond the field clobbering, a beacon flips `in_flight = st in (1,2)` to False and **unlocks the locked AGL baseline mid-flight** (`model.py:70-77`; verified: `locked_baseline −84 → None`), after which the next telemetry packet re-locks from a window polluted with in-flight altitudes. **`CALL` capture must NOT become telemetry-only** — the callsign arrives on the beacon (`model.py:61`). |
| `ground/oled/spec.py`, `render.py` | **No, transitively** | They consume `view_model`; fixing row E fixes the hero blanking to `"--"` and the state band to `"?"`. |
| `ground/panel/*` (LEDs, heartbeat) | **No** | `last_rx_ts`/`G_RX` advancing on a beacon is **correct**. `crc_climbing`/`rf_foreign` are not published by ingest today, so `B_RF` is unaffected either way. |
| `ground/publish/data.py` | **No** | It publishes the canonical derived index, which §1.1 shows is currently protected. It stops being protected by accident (row B) and starts being protected by rule. Its CSV input is row F's, which does change. |
| `ground/sessionlog/records.py` | **No** | It records every frame verbatim and classifies nothing. That is correct and must stay correct — D1 depends on it. |

---

## 6. Absent is not zero (the half that `FT` does not fix)

Classification stops *beacons* from being read as telemetry. It does **not** stop a telemetry
frame with a legitimately absent field from being read as a zero — and ADR 0001 explicitly
permits absent fields on telemetry frames (the lander, `SRC:2`, may have no `ALT` at all).

**Proposed rule, ground-side, in this ADR:** a receiver must never substitute a numeric default
for an absent field. Specifically:

- absent `ALT` ⇒ the sample contributes **nothing** to `peak_alt` or to the baseline window
  (`pad_baseline` already skips `None` — `ground/flights/baseline.py:29` — so the window logic
  is ready; it is the callers that inject the zero).
- absent `SEQ` ⇒ **no** gap arithmetic and **no** `last_seq` update, exactly as census row C
  already does.
- a frame with neither is still recorded raw and still counts as RX; it simply contributes to
  no derived statistic.

This is cheap, it is ground-side only, and — importantly — **it is the fix that can ship before
any wire change**, because it makes the ground station survive a beacon *before* a beacon
exists on the air. See §8 step 0.

> **RELATED BUT DELIBERATELY NOT DECIDED HERE.** Whether the *wire format* should gain an
> explicit "absent" representation distinct from zero is a **separate question already recorded
> in the backlog** (on the working branch — not visible from this base commit, see the header).
> This ADR does not answer it, prejudge it, or depend on either outcome. The rule above is about
> what a receiver does with a tag that is simply not present — which ADR 0001 already defines as
> legal. A wire-level absent representation would be an additional, independent change with its
> own airtime and encoder costs.

---

## 7. Should non-telemetry frames carry `SEQ`?

**Recommendation: no. `SEQ` belongs to the telemetry sequence space and nothing else.**

The trade-off is real and worth stating in full:

- **A shared counter is actively wrong.** If a beacon consumes a sequence number and consumers
  correctly skip the beacon, the skipped number reads as a **lost telemetry packet** — a
  fabricated gap in `LinkStats` and in `packets_lost`, in the published loss percentage, from
  correct behaviour. Classification does not save you here; it *causes* the hole. This is the
  same corruption as §1.1 arriving by a different route.
- **A separate counter costs you nothing you have.** With no counter, you cannot detect a *lost*
  beacon — you cannot distinguish "the sled stopped identifying" from "the ID frame was
  dropped". That sounds serious for a Part-97 obligation and is not, because **the ID obligation
  is on the transmitter, not the receiver.** A beacon lost in the air is a link event, not a
  compliance failure. And the `id` advisory events (census row D) already carry timestamps, so
  **ID cadence is observable directly from the session log** — a >10 min gap between `id` events
  is detectable without any counter at all.
- **You are not foreclosing it.** If beacon-loss detection ever earns its way in, a per-type
  counter is *itself* an additive, no-bump change under ADR 0001. It must use its **own tag**
  (`IDSEQ`/`DSEQ`, per Appendix A's "prefer multi-character names"), never `SEQ`.

**Corollary for the C2 dump frame:** ordering and completeness matter far more for a replay than
for a beacon — a dump with a missing chunk is a corrupt record, not a missed hello. But it still
must not use `SEQ`, for exactly the reason above. Its counter (if any) is C2's decision, not
this ADR's; see Open Questions.

---

## 8. Migration

The ordering constraint is the point: **the ground station must survive a beacon before a
beacon exists on the air.** The existing sled emits no `FT`, and the golden vector, the C
encoder test, `test_v1.py::GOLDEN`, and the F1 real-RF fixture must all keep passing unchanged.

**Step 0 — ground-only, no wire change, no ADR edit. Ships first, independently.**
Remove the absent→zero coercions (§6) and give rows A and B one shared filter. Fixes the
measured corruption *today*, and — because `absent ⇒ TELEMETRY` — has zero effect on any frame
the fleet currently emits. Acceptance: the F1 golden numbers are byte-identical
(`peak_alt_ft −74`, `packets_lost 1`, `baseline_ft −84`, `packets_rx 75`), plus the new
live-vs-derive equivalence test from §4.2.

**Step 1 — the ADR 0001 amendment.** One normative row (`FT`), one new frame-type registry
subsection, the two new rules (unknown `FT` value is not telemetry; a classification failure is
counted, not dropped), and a **second golden vector** for the beacon frame. The existing golden
vector is **not touched** — that is what keeps `firmware/test/test_packet` and
`ground/decode/tests/test_v1.py::GOLDEN` green with no edits. Per ADR 0001's lockstep rule, the
ADR edit precedes both implementations.

**Step 2 — ground implements `FT`.** `frame_type()` + typed fan-out (§4.2), retiring all six
census rows. The beacon golden vector becomes a decoder fixture, and — filling the gap noted in
§1.2 — the **first standalone beacon test the ground side has ever had**.

**Step 3 — firmware emits beacons (Epic 6 rider 4).** `encode_packet` in
`firmware/lib/packet/packet.cpp` is a single fixed `snprintf` and **is not modified**; the
beacon gets its own pure encoder function in the same `lib/` unit, host-tested against the new
golden vector under `pio test -e native`. `firmware/src/main.cpp` calls it on the Epic 6 ID
schedule.

**Step 4 — re-run the standing e2e gate** (sled TX → `ground/rx/` driver → payload matches the
ADR fixtures), which `RESUME.md` marks as a required gate for anything touching encode/decode.
Steps 1-3 all touch it.

**What is NOT protected by this migration, and should be said out loud:** any
`flights-snapshot.json` or `flight_close` event recorded by a pre-fix service during a session
that contained a beacon carries wrong stats permanently, and any per-flight CSV exported from
such a session carries row F's empty rows. The canonical index rebuilds correctly from the raw
session log (raw is always persisted), so **nothing is lost** — but the advisory artifacts and
exports from such a session are not trustworthy and should be regenerated, not read.

---

## 9. Consequences

**Accepted trade-offs**
- One more concept for every receiver author, including the Epic 8 handheld parser: *classify,
  then interpret*. (Against: they are already doing it, six ways, without knowing it.)
- Frame types become a registry that must be extended in lockstep, like `St` codes.
- Row B's change alters behaviour for a case that has never occurred (an `FT:0` frame with no
  `St`) — correctly, but it is a behaviour change, not purely a bug fix.
- Rule 3 (count what you exclude) means new anomaly counters and new advisory events, i.e. more
  event volume in the session log.

**Gains**
- Six private definitions of "telemetry frame" become one, in the contract.
- The published loss percentage and peak altitude stop depending on an undocumented accident.
- Live and canonical paths become provably equal on the same input.
- Epic 7's lander (no `ALT`) and backlog C2's dump frame both become expressible without any
  further contract change — and the lander stops being silently droppable (§2.1).
- ADR 0001's additive-extension promise survives contact with a second frame shape.

---

## 10. Open questions

Each with the trigger that should force a decision. **None of these should be resolved inline.**

1. **Does the `ID` beacon need to be a standalone frame at all?** Epic 6 rider 4 says
   "`CALL:<callsign>` at TX start / ≤9.5 min / graceful shutdown" — which is *also* satisfiable
   by appending `CALL` to an ordinary telemetry frame, which is exactly what every existing test
   already models (§1.2) and which causes **none** of the failures in §1.1. That would make the
   `ID` frame type unnecessary for Epic 6 — though **not** for Epic 7's lander or C2's dump,
   which need classification regardless, and **not** for the census, which is broken today
   independently of whether a beacon ever flies.
   **Trigger: Epic 6 rider 4 reaching design.** It must be settled before firmware emits
   anything.
   *(Note the shutdown case: a graceful-shutdown ID cannot ride a telemetry frame if the reason
   for shutdown is that telemetry has stopped.)*

2. **Does the C2 dump frame need its own sequence/ordering tag?** §7 says it must not use `SEQ`;
   it does not say what it uses instead, because a replay's chunking scheme is C2's design.
   **Trigger: C2 leaving the backlog.**

3. **Should an unknown-`FT` frame raise an operator signal, or only a log line?** Rule 3
   requires it be counted; it does not say whether it reaches the panel. It is the same class as
   `foreign_sys`/`unknown_src`, which are advisory-only today; `B_RF` exists but ingest publishes
   neither `crc_climbing` nor `rf_foreign` into the heartbeat, so the panel currently cannot show
   it. **Trigger: the first non-telemetry frame flying, or any work that wires
   `crc_climbing`/`rf_foreign` into `state_snapshot`.**

4. **Should `decoded` be split into `telemetry_decoded` vs `frames_decoded`?** Today
   `core.decoded` counts every accepted frame, driving both the `service_stop` summary and the
   `last_rx_ts` freshness the panel uses. The freshness use is *correct* on beacons; the summary
   use is not. **Trigger: implementing typed fan-out (§4.2 option b).**

5. **Does `ObserverRegistry.dispatch`'s silent `except Exception: pass` deserve the same
   treatment as row B?** §2.1 names them as the same failure class, and this ADR fixes only the
   frame-drop half. A dispatch-failure counter is a two-line change with the same justification.
   **Deliberately out of scope here** — it is not a contract question and belongs on its own
   branch. **Trigger: any consumer failing silently in the field, or the next time a consumer is
   added to the registry.**

6. **Does `FT` belong in `docs/telemetry-dictionary.md` as a tag, or as a new section?** It is
   the first v1 tag that is *about the frame* rather than about the vehicle.
   **Trigger: the ADR 0001 amendment PR.**

7. **Do the two backlog items cited here match their entries on the working branch?** This draft
   was written at `6f8f5e9`, where **backlog C2** and the **wire-level absent-vs-zero** question
   are not present; both are cited from session context (see the header). **Trigger: accepting
   this ADR** — reconcile the citations against the working branch first.
