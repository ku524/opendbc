# Port Status - Sonata LF Hybrid longitudinal on sunnypilot

**Branch:** `sonata-lf-hev-long-sp`
**Base commit:** `ffa13083` (sunnypilot/opendbc master)
**Baseline implementation HEAD:** `675f988d`
**Review-hardened implementation:** `15ad0815eb1dd1895f0b3584e0cddf7dbc4dc0aa`
**Device-tested port:** `f62fb8fe18d24c06c08755cab966d86b8b94e37d` on base `b9712d20`

## Done (committed)

| Plan task | Commit | What |
|---|---|---|
| Task 1 | `c63a1158` | Added `HyundaiSafetyFlags.ALT_STANDSTILL = 1024` |
| Task 2 | `e2ab5806` | Decoded `HYUNDAI_PARAM_ALT_STANDSTILL` in `hyundai_common.h` |
| Task 3 | `418995e7` | Relaxed only 0x386 in long/non-long RX checks and sourced moving state from TCS13 |
| Task 4 | `6aefd30d` | Registered `HYUNDAI_SONATA_LF_HYBRID` and wired the MAIN safety param |
| Task 5 | `92116d81` | Added long/non-long ALT_STANDSTILL safety coverage |
| Task 6 | `1cf8c8cb` | Added the sunnypilot-compatible offline replay script |
| Review hardening | `e68ba8df` | Pinned and snapshotted canonical replay inputs, validated TCS13/timeline/cadence, and added negative controls |
| Lifecycle cleanup | `89a50b75` | Restored CP/SP deinit API, radar re-enable cleanup, and ALT RX precedence coverage |
| Exception-safe cleanup | `6d6bf2c5` | Made PandaRunner initialization and exit cleanup best-effort while preserving primary exceptions |
| Lifecycle fault coverage | `15ad0815` | Covered partial interface initialization and failure of every cleanup stage |

## Verification

The following results were rerun from the immutable hardening revision `15ad0815eb1dd1895f0b3584e0cddf7dbc4dc0aa`:

- `opendbc.safety.tests.test_hyundai`: 1,938 tests passed, 208 skipped.
- `opendbc/safety/tests/test.sh`: 8,421 tests passed, 911 skipped; checked C files reached 100% line coverage.
- Hyundai car tests: 14 passed, 2 skipped.
- Route, platform config, Sonata interface, and lateral-limit focused tests: 5 passed.
- Target Python files pass `ruff`, `ty check`, and `py_compile`; all 23 replay regression tests pass.
- All 267 car-interface tests pass; all 9 PandaRunner lifecycle tests and focused Hyundai/signature tests pass.
- Empty-fingerprint CarParams checks confirm standard Hyundai safety, LONG boundary behavior, HYBRID_GAS and ALT_STANDSTILL, with ESCC/NON_SCC off.
- `carcontroller.py`, `hyundaican.py`, and `carstate.py` remain zero-diff.

## Adversarial Review Hardening

- Replay validation contains no `assert`; `/dev/null`, empty rlogs, one segment, duplicate segments, and another route all exit nonzero under `python -O` without a success banner.
- Exact route filenames/segment set, path/inode/content uniqueness, canonical per-segment SHA-256, authenticated content snapshots, raw and cross-segment timestamp order, minimum capture size/duration, required bus/address/length/unique-timestamp rate/edge-inclusive max-gap, and forbidden ESCC/LDA/FCA addresses are checked before replay.
- CarParams and SP flags are derived from the recorded fingerprint rather than an empty fingerprint.
- TCS13 checksum/counter integrity is checked with the same fields and tolerance as host safety before polarity analysis.
- StandStill polarity processes each unique timestamp once, resets parser/wheel state per segment, accepts only nonnegative wheel/TCS13 skew within 100 ms, and enforces minimum stopped/moving cohorts.
- Safety negative controls separately cover ALT-off 0x386 checksum and fixed-counter failures in long/non-long, fixed-counter TCS13, and independent SCC11/SCC12 requirements. SP param is reset before every safety hook setup.
- LONG/non-long ALT RX configurations are valid across FCEV/LDA/ESCC/NON_SCC flag combinations; every LONG required RX group and non-long SCC11/SCC12 requirement is independently enforced while TCS13 remains strict.
- Base, Hyundai, Honda, Toyota, and Subaru deinit APIs preserve `CP_SP`. `PandaRunner` attempts diagnostic mode, ECU re-enable, no-output, and panda reset independently on initialization and exit failures. Cleanup errors cannot mask an initialization or body exception; normal-exit cleanup still reports the first failure after reset is attempted.
- The personal-fork car docs render as `Community/#community` rather than `Upstream`.
- The unsupported MANDO radar-track claim was withdrawn; the canonical segments independently contain zero bus-1 0x500-0x535 frames.
- Canonical route replay passed: 18,121 CAN events, 9,065 integrity-valid TCS13 frames, stopped `3044/3098` (98.26%), moving `5031/5031` (100%).

This checkout has no standalone `SConstruct`, so the stale `scons -j8 opendbc/safety` command is not an available entrypoint. Safety tests compile `libsafety.so` directly with `cc`; both targeted and full coverage gates passed through that repository-native path.

## Device and On-Car Validation

- Task 7 Steps 1 through 4 are complete. Revision `f62fb8fe` was file-deployed onto sunnypilot `staging@3781e253`.
- Panda firmware was rebuilt and auto-reflashed. Active signed-binary SHA-256 is `095e3486bf09b42a6d26ce40ab6be55fd0115dc8aefd7181a0187bbfcfc585f1`.
- Alpha Longitudinal was enabled and a 25-minute raw-CAN road-test range was captured.
- Radar-disable gate passed: zero stock SCC source-0 frames, openpilot SCC11/SCC12 at about 50 Hz, tester-present at about 1 Hz, and no dual SCC.
- Panda RX invalid/fault counts, CAN invalid/timeouts, permanent steering faults, stock AEB, and stock FCW were zero.
- Standstill/resume, brake disengagement, and gas override were exercised. Intermediate disengagements were driver-initiated.
- All required route logs and recovery artifacts were copied to the laptop and verified by SHA-256. See `2026-07-11-sonata-lf-hev-long-device-handoff.md`.

## Remaining Gate

- Task 7 Step 5 remains open only for the driver's subjective review: unintended acceleration/braking, launch strength, override feel, warnings, and comfort.
- The active main-repository `radard.py` experiment is preserved but not proven necessary. It requires a clean-boot A/B without external message subscribers and must not be included in the opendbc PR.

## Resume

1. Analyze the copied route and correlate the driver's subjective observations.
2. Integrate the deployed `f62fb8fe` opendbc history into the personal branch, then rerun focused safety, interface, lifecycle, and replay gates.
3. Keep firmware, Params, route evidence, and unproven main-repository diagnostics outside the personal opendbc PR.

This is a personal fork change. Do not open an upstream PR against sunnypilot or commaai.
