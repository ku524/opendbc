# Handoff - Sonata LF Hybrid longitudinal sunnypilot port

## Done

- Tasks 1 through 6 remain implemented on personal branch `sonata-lf-hev-long-sp` at remote revision `13737ba0`.
- Device-compatible opendbc work is preserved on `sonata-lf-hev-long-sp-device-b971` at `f62fb8fe`, with a complete verified Git bundle.
- Task 7 Steps 1 through 4 are complete: source deployment, device build, panda auto-reflash verification, and Alpha Longitudinal enablement.
- A long urban-road drive exercised engagement, deliberate disengagement, standstill/resume, brake disengagement, and gas override.
- Required route evidence, active source patch, Params, exact firmware, pre-custom rollback, and experimental radard originals were copied to `/Users/mark.yeon/Documents/work/oss/sunny_opendbc-device-backups`.
- Complete device modification, rollback, artifact, and PR-integration record: `docs/superpowers/plans/2026-07-11-sonata-lf-hev-long-device-handoff.md`.
- Driver feedback and full-rlog analysis identified fixed `LongControl` starting/stopping commands as the ride-quality trigger.
- Local follow-up commits `681f9aaa` and `9c3031f0` restore the deployed LKAS HUD behavior and add an LF Hybrid-only smooth start/stop candidate.
- Local commit `bc54535e` enables route-verified Mando tracks and sets `steerRatio=16.4`.
- The different-laptop resume prompt is `docs/superpowers/plans/2026-07-14-sonata-lf-hev-followup-laptop-deployment-prompt.md`; its staged vehicle procedure is `2026-07-11-sonata-lf-hev-on-car-validation-checklist.md`.

## Current State

- Device sunnypilot: `staging@3781e253`, intentionally dirty from file deployment.
- Active opendbc files exactly match local `f62fb8fe`.
- Active panda firmware SHA-256: `095e3486bf09b42a6d26ce40ab6be55fd0115dc8aefd7181a0187bbfcfc585f1`.
- Active `radard.py` is the poll-all candidate, SHA-256 `8dc45dfcea53fdac181d875cd3abc72913b8cbd8d745de7ea3a0aebca572a865`.
- Handoff Params: Alpha Long on, Always Offroad on, device offroad, Experimental Mode off.
- No comma device was contacted during the at-home analysis.
- Local follow-up branch `followup/sonata-lf-hev-long` contains the code candidate at `bc54535e`; it has not been pushed or deployed.
- The HUD source now matches deployed `f62fb8fe`; the ride-quality tune is offline-only and unverified on-car.

## Verification

- Route `000000e4--5ae02c8c77`, segments 0, 9, and 17 through 45, has qlog+rlog preserved in a 62-entry tar.
- Local and device route tar SHA-256 matched: `31e317d1dc0965f1d686afc805b690ae74896b150a9a1dd5c082c58a7d164c14`.
- Git bundle verification reported complete history.
- Road-test raw CAN: zero stock SCC, openpilot SCC11/SCC12 at about 50 Hz, tester-present at about 1 Hz, no dual SCC.
- Panda RX invalid/fault, CAN invalid/timeout, permanent steer fault, stock AEB, and stock FCW counts were zero.
- Road-test service validity was 100% after diagnostic subscribers were stopped.
- Eleven active lead-following launches showed planner acceleration median `0.444 m/s²`, but `LongControl` requested fixed `1.0 m/s²` in every case.
- Nine active lead-following stops showed planner acceleration median `-0.036 m/s²`, while `LongControl` requested median `-1.753 m/s²` and reached about `-2.0 m/s²`.
- Follow-up gates pass: Hyundai safety 1,938 tests/208 skipped; Hyundai car 19/2 skipped; radar interface 4; PandaRunner 9; car interface 267; replay regression 23; targeted `ruff`, `ty`, and `py_compile`.
- Backed-up Alpha Long rlogs contain 1,189,330 Mando track frames across all 32 addresses after SCC normal-communication disable; current RadarInterface replay ends valid on all 31 segments.
- Highway-route steering evidence supports `16.4`: qualified median `16.402`, left/right `16.405/16.372`, and last-20-minute median `16.404`.

## Decisions and Caveats

- `radard.py` is not part of opendbc and its necessity is unproven. Preserve it, but do not merge it before a clean-boot A/B with no diagnostic message subscribers.
- The intermittent communication issue correlated with diagnostic SubMaster reader-slot exhaustion and stopped when those subscribers stopped. Original radard had already passed a clean 225-second session.
- The harmful "live monitor" was repeated short-lived Python `SubMaster` diagnostics. msgq has 15 reader slots per service, subscriber close does not release a slot, and the 16th subscription evicts all readers. Never repeat live subscribers during validation; use offline qlog/rlog. Any touched session is contaminated until a full vehicle OFF/ON cycle and new route.
- Draft PR `ku524/opendbc#1` remains at remote head `13737ba0`. The local follow-up branch contains the deployed HUD fix, but is not pushed and is not a proven deployable unit.
- The LF Hybrid candidate keeps `stopAccel=-2.0`, disables the fixed starting state, and reduces `stoppingDecelRate` from `0.8` to `0.45`. It does not change panda safety or CAN message formats.
- The candidate uses `steerRatio=16.4` and `MANDO_RADAR`. Full RadarD lead fusion and false-lead behavior remain on-car gates; enabling tracks does not restore factory AEB.
- Do not commit panda binaries, Params, logs, or reverted diagnostic patches to the personal PR.
- Do not comma-reboot while vehicle ignition stays on after radar disable. Use a full vehicle OFF/ON cycle to reset the radar ECU.

## Remaining

1. Start the vehicle-side laptop session with `2026-07-14-sonata-lf-hev-followup-laptop-deployment-prompt.md`, then follow the linked on-car checklist.
2. Run Mando lead-selection plus matched `Off`/`Dynamic` checks; factory AEB remains unavailable while the stock radar is disabled.
3. Restore original `radard.py`, use a full vehicle OFF/ON cycle, and complete the clean no-external-subscriber PR-only A/B.
4. Validate the new static `steerRatio=16.4` during the same route without changing lateral torque limits.
