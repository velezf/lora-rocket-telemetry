# Epic 5.1 — integrity note: the evidence is not reproducible from the repo

**Written 2026-08-06. Base commit `ca99691`.** This note records a gap between a claim and the
repository that is supposed to support it. It is not a defect report and nothing is broken;
Epic 5.1's result is probably correct. The problem is narrower and worth stating exactly: **a
fresh checkout of this repo cannot rebuild the artifact that produced the evidence.**

## 1. What is claimed

`docs/RESUME.md` §Epic status, Epic 5:

> 🟡 **5.1 hardware evidence done** (LSM6DSOX 0x6a + LIS3MDL 0x1c on the sled bus; WHO_AM_I
> 0x6C/0x3D; sane gyro/mag). 5.2–5.4 not started.

`docs/PROJECT_PLAN.md` Epic 5 defines 5.1 as *"Hardware: chain the 9-DoF onto the sled's STEMMA
QT I²C bus; confirm reads"*. The claim is therefore: **the two sensors were addressed, identified
by WHO_AM_I, and read plausibly, on the sled's bus.**

## 2. What the repo actually declares

`firmware/platformio.ini` `[env:feather_m0_tx]`, in full, at `ca99691`:

```ini
lib_deps =
    mikem/RadioHead@1.120.0
    adafruit/Adafruit BMP3XX Library@2.1.6
    adafruit/Adafruit ADXL375@1.1.2
    adafruit/Adafruit Unified Sensor@1.1.15
```

**No LSM6DSOX library. No LIS3MDL library.** The `[env:native]` env declares no dependencies at
all and is required to stay that way by design. There is no third env.

The gap is wider than `lib_deps`. Searching the tracked tree for any 9-DoF code:

- `grep -rniE "lsm|lis3mdl|9-dof|9dof" firmware/ RocketLoRaTelemetry/` → **no matches.**
- `firmware/lib/` contains exactly `apogee/`, `convert/`, `launch/`, `packet/`, `README`.
- `firmware/src/` contains exactly `main.cpp`.
- `docs/bench-sessions.md`, the append-only provenance register, has **no row** for the 5.1 smoke
  test. (It registers *ground-station* sessions, so this is arguably out of its scope — but it
  means the repo has no provenance record of the session either.)

**So the sketch that produced WHO_AM_I `0x6C`/`0x3D` does not exist in this repository in any
form** — not as a source file, not as an env, not as a declared dependency, not as a logged
session. It was almost certainly a scratch sketch (Arduino IDE or a local PlatformIO env) that
was never committed.

**The brief for this note is confirmed, not contradicted.** One qualification, in the repo's
favour: the gap is **already flagged in two places** — `docs/RESUME.md` §Hardware state ("Its
libraries are **NOT in `platformio.ini` yet** — Epic 5 owns adding `Adafruit_LSM6DSOX`/`_LIS3MDL`")
and `docs/HANDOFF.md` ("libs NOT yet in platformio.ini — Epic 5 owns that"). Nobody hid anything.
What is missing is not the fact but **its consequence**, which neither note draws.

## 3. Why the gap matters

This project's stated evidence standard is that **evidence must describe the running artifact** —
the rule that forced the `0xAE` reseat test to be re-run, because removing one byte made the
deployed binary a different binary and the earlier evidence no longer covered it.

Epic 5.1 fails a weaker precondition than that one. It is not that the evidence describes a
*different* artifact; it is that **the artifact cannot be identified at all.** Concretely:

1. **No git SHA describes the binary that produced the reading.** There is nothing to cite.
2. **The result cannot be re-run.** `pio run -e feather_m0_tx` at any commit, past or future,
   builds firmware with no 9-DoF code in it. A second person with the same hardware and this
   repo has to rewrite the sketch before they can attempt to reproduce anything.
3. **A regression is undetectable.** If the LIS3MDL were on `0x1e` rather than `0x1c` (both are
   valid addresses for that part depending on the SDO/SA1 pin), or if a chained cable had been
   swapped since, nothing in the repo would notice.
4. **It is the same shape as the failure class this project already named** — *a check that
   looked like it was checking*. That class is about guards that cannot fail; this is its
   sibling: **a result that cannot be re-attempted.** In both cases the artifact reads as
   green and the green means less than it appears to.

**Proportionality, stated plainly so this note is not over-read.** The consequence here is
small. A WHO_AM_I readback is a low-stakes, easily repeated bench check; nothing downstream
depends on it, since 5.2–5.4 are not started and no packet field carries 9-DoF data. It is
recorded because the *standard* is the project's asset, and a standard that is applied to a
peripheral reseat but not to an epic's status line is not yet a standard.

## 4. What closes it

Either of the following. **Option A is the honest cheap fix; option B is the real one.**

**Option A — restate the claim to match what exists (minutes, no hardware).**
Amend the Epic 5 status line to say what was actually done and what was not: *"5.1 smoke-read
once on the bench from an uncommitted sketch; **not reproducible from this repo**, and to be
re-established under 5.2 when the libraries land."* This costs nothing and removes the
overclaim. It does not produce evidence — it stops asserting evidence the repo cannot support.

**Option B — make it reproducible (needs the sled, so it is hardware-gated).**

1. Add `adafruit/Adafruit LSM6DS` and `adafruit/Adafruit LIS3MDL` to `lib_deps` in
   `[env:feather_m0_tx]`, **version-pinned** like every existing entry. `[env:native]` stays
   dependency-free — the `lib/` purity rule is unaffected, since none of this is pure logic.
2. Commit the probe as a real, buildable artifact in `firmware/src/` — either folded into
   `main.cpp` behind a build flag, or as its own PlatformIO env — so that `pio run` produces the
   binary that does the reading.
3. Re-run the smoke test on the sled and record it with the **git SHA plus the size and hash of
   the `.bin`**, per the project's own evidence rule. Record the observed addresses and WHO_AM_I
   values as *output of that binary*, not as remembered numbers.
4. Only then may the status line read "5.1 done" without qualification.

**Until one of these lands, "5.1 hardware evidence done" overstates what the repository can
support.** The reading almost certainly happened and was almost certainly right — but *almost
certainly* is what a reproducible artifact exists to replace.

## 5. The generalisable rule

**A status line that claims hardware evidence must name the artifact that produced it, and that
artifact must be buildable from the repo at a commit.** If it cannot be, the correct status is
not "done" but "observed once, not reproducible" — which is a real and useful state, and the only
honest one when the sketch was never committed.
