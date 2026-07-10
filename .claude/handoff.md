# Handoff - Sonata LF Hybrid longitudinal sunnypilot port

## Done

- Tasks 1 through 6 remain implemented on personal branch `sonata-lf-hev-long-sp` at `e5a55c9e`.
- Device-compatible opendbc work is preserved on `sonata-lf-hev-long-sp-device-b971` at `f62fb8fe`, with a complete verified Git bundle.
- Task 7 Steps 1 through 4 are complete: source deployment, device build, panda auto-reflash verification, and Alpha Longitudinal enablement.
- A long urban-road drive exercised engagement, deliberate disengagement, standstill/resume, brake disengagement, and gas override.
- Required route evidence, active source patch, Params, exact firmware, pre-custom rollback, and experimental radard originals were copied to `/Users/mark.yeon/Documents/work/oss/sunny_opendbc-device-backups`.
- Complete device modification, rollback, artifact, and PR-integration record: `docs/superpowers/plans/2026-07-11-sonata-lf-hev-long-device-handoff.md`.

## Current State

- Device sunnypilot: `staging@3781e253`, intentionally dirty from file deployment.
- Active opendbc files exactly match local `f62fb8fe`.
- Active panda firmware SHA-256: `095e3486bf09b42a6d26ce40ab6be55fd0115dc8aefd7181a0187bbfcfc585f1`.
- Active `radard.py` is the poll-all candidate, SHA-256 `8dc45dfcea53fdac181d875cd3abc72913b8cbd8d745de7ea3a0aebca572a865`.
- Handoff Params: Alpha Long on, Always Offroad on, device offroad, Experimental Mode off.
- No more direct device work is required for route analysis.

## Verification

- Route `000000e4--5ae02c8c77`, segments 0, 9, and 17 through 45, has qlog+rlog preserved in a 62-entry tar.
- Local and device route tar SHA-256 matched: `31e317d1dc0965f1d686afc805b690ae74896b150a9a1dd5c082c58a7d164c14`.
- Git bundle verification reported complete history.
- Road-test raw CAN: zero stock SCC, openpilot SCC11/SCC12 at about 50 Hz, tester-present at about 1 Hz, no dual SCC.
- Panda RX invalid/fault, CAN invalid/timeout, permanent steer fault, stock AEB, and stock FCW counts were zero.
- Road-test service validity was 100% after diagnostic subscribers were stopped.

## Decisions and Caveats

- `radard.py` is not part of opendbc and its necessity is unproven. Preserve it, but do not merge it before a clean-boot A/B with no diagnostic message subscribers.
- The intermittent communication issue correlated with diagnostic SubMaster reader-slot exhaustion and stopped when those subscribers stopped. Original radard had already passed a clean 225-second session.
- The harmful "live monitor" was repeated short-lived Python `SubMaster` diagnostics. msgq has 15 reader slots per service, subscriber close does not release a slot, and the 16th subscription evicts all readers. Never repeat live subscribers during validation; use offline qlog/rlog. Any touched session is contaminated until a full vehicle OFF/ON cycle and new route.
- Draft PR `ku524/opendbc#1` at `e5a55c9e` is not yet identical to deployed `f62fb8fe`: the deployed LKAS HUD preservation change is absent, the device branch is unpushed, and PR-only runtime with original radard has not completed a clean A/B.
- Do not commit panda binaries, Params, logs, or reverted diagnostic patches to the personal PR.
- Do not comma-reboot while vehicle ignition stays on after radar disable. Use a full vehicle OFF/ON cycle to reset the radar ECU.

## Remaining

1. Record subjective impressions: unintended acceleration/braking, launch strength, brake/gas override feel, warnings, and comfort.
2. Analyze copied route evidence against those observations.
3. Integrate the eight deployed opendbc commits through `f62fb8fe` into the updated personal branch.
4. Rerun focused safety, Hyundai interface, lifecycle, and replay tests before updating the personal PR.
