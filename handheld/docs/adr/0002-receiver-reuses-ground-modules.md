# ADR 0002 — The receiver runs from the repo checkout and reuses ground modules

- **Status:** Accepted
- **Date:** 2026-08-31
- **Scope:** Epic 8.2 — receiver firmware architecture

## Context

The handheld needs three things the ground station already has, each with a
single existing authority:

- the **v1 decoder** — `ground/decode/v1.py`, pure by design ("runs identically
  on Mac and Pi");
- the **RF constants** — `ground/rx/sx127x.py::LoRaConfig` (itself citing
  ADR 0005 §7 of the main repo), whose failure mode when duplicated is silent
  total link loss, now across THREE nodes;
- the **AGL pad baseline** — `ground/flights/baseline.py::pad_baseline`, the
  same stability-gated zero the ground live path locks at flight_open. First
  bench (2026-08-31) showed why: raw baro read −85 ft on the pad.

Writing handheld copies of any of these is the restated-fact hazard this
project keeps paying for (see "Cite, don't restate" in `CLAUDE.md`).

## Decision

**No handheld copies. The app (`handheld/app/`) imports the ground modules
directly, with the repo root on `sys.path`** — the project deliberately keeps
`ground` unpackaged (the repo-root `pyproject.toml` is the portfolio render
env, not a runtime), so the handheld follows the same run-from-checkout
convention rather than inventing packaging.

Consequences:

- **Deploy is the sanctioned git path** (`CLAUDE.md` → "Deploying to
  `apogee-gs`", which Epic 8 explicitly inherits): the Zero holds a clone at
  `~/lora-rocket-telemetry`; deploys are `git pull`, never file copies.
- **The Blinka env stays separate** (`~/radio`, mirroring
  `handheld/pyproject.toml`): hardware deps live in the uv venv, repo code in
  the checkout. `apogee-handheld.service` runs
  `~/radio/.venv/bin/python -m handheld.app.main` with the checkout as cwd.
- **Layering:** viewmodel/render/rx/loop are pure and host-tested from
  `handheld/tests/` (the repo `.venv-test`); `main.py` is deliberately thin
  untested Blinka glue — the same seam discipline as `ground/panel/`.
- The display heartbeat re-sends its recovery preamble every frame and pins
  `0xAE` out by test — the ground OLED lesson (`docs/RESUME.md`, "What the
  OLED fix taught") encoded as a failing-capable check, not a convention.

## Alternatives rejected

- **Vendored copies** of decoder/config/baseline: three restated contracts
  that drift silently; the BW constant alone makes this disqualifying.
- **Packaging `ground` as a library**: solves the same problem with more
  machinery than the project wants, and diverges from how the ground station
  itself runs.
