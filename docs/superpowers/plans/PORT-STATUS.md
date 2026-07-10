# Port Status - Sonata LF Hybrid longitudinal on sunnypilot

**Branch:** `sonata-lf-hev-long-sp`
**Base commit:** `ffa13083` (sunnypilot/opendbc master)
**Baseline implementation HEAD:** `675f988d`
**Review-hardened implementation:** latest branch HEAD

## Done (committed)

| Plan task | Commit | What |
|---|---|---|
| Task 1 | `c63a1158` | Added `HyundaiSafetyFlags.ALT_STANDSTILL = 1024` |
| Task 2 | `e2ab5806` | Decoded `HYUNDAI_PARAM_ALT_STANDSTILL` in `hyundai_common.h` |
| Task 3 | `418995e7` | Relaxed only 0x386 in long/non-long RX checks and sourced moving state from TCS13 |
| Task 4 | `6aefd30d` | Registered `HYUNDAI_SONATA_LF_HYBRID` and wired the MAIN safety param |
| Task 5 | `92116d81` | Added long/non-long ALT_STANDSTILL safety coverage |
| Task 6 | `1cf8c8cb` | Added the sunnypilot-compatible offline replay script |

## Verification

- `opendbc.safety.tests.test_hyundai`: 1,935 tests passed, 208 skipped.
- `opendbc/safety/tests/test.sh`: 8,418 tests passed, 911 skipped; checked C files reached 100% line coverage.
- Hyundai car tests: 14 passed, 2 skipped.
- Route, platform config, Sonata interface, and lateral-limit focused tests: 5 passed.
- Target Python files pass `ruff` and `ty check`; all 22 replay regression tests pass.
- Empty-fingerprint CarParams checks confirm standard Hyundai safety, LONG boundary behavior, HYBRID_GAS and ALT_STANDSTILL, with ESCC/NON_SCC off.
- `carcontroller.py`, `hyundaican.py`, and `carstate.py` remain zero-diff.

## Adversarial Review Hardening

- Replay validation contains no `assert`; `/dev/null`, empty rlogs, one segment, duplicate segments, and another route all exit nonzero under `python -O` without a success banner.
- Exact route filenames/segment set, path/inode/content uniqueness, canonical per-segment SHA-256, authenticated content snapshots, raw and cross-segment timestamp order, minimum capture size/duration, required bus/address/length/unique-timestamp rate/edge-inclusive max-gap, and forbidden ESCC/LDA/FCA addresses are checked before replay.
- CarParams and SP flags are derived from the recorded fingerprint rather than an empty fingerprint.
- TCS13 checksum/counter integrity is checked with the same fields and tolerance as host safety before polarity analysis.
- StandStill polarity processes each unique timestamp once, resets parser/wheel state per segment, accepts only nonnegative wheel/TCS13 skew within 100 ms, and enforces minimum stopped/moving cohorts.
- Safety negative controls separately cover ALT-off 0x386 checksum and fixed-counter failures in long/non-long, fixed-counter TCS13, and independent SCC11/SCC12 requirements. SP param is reset before every safety hook setup.
- The personal-fork car docs render as `Community/#community` rather than `Upstream`.
- The unsupported MANDO radar-track claim was withdrawn; the canonical segments independently contain zero bus-1 0x500-0x535 frames.
- Canonical route replay passed: 18,121 CAN events, 9,065 integrity-valid TCS13 frames, stopped `3044/3098` (98.26%), moving `5031/5031` (100%).

This checkout has no standalone `SConstruct`, so the stale `scons -j8 opendbc/safety` command is not an available entrypoint. Safety tests compile `libsafety.so` directly with `cc`; both targeted and full coverage gates passed through that repository-native path.

## Deferred Gates

- Task 7 device deployment, panda rebuild/reflash, radar-disable confirmation, and on-car validation remain manual and safety-critical.

## Resume

1. Preserve the passing canonical replay result as the offline prerequisite.
2. Perform Task 7 from `2026-07-10-sonata-lf-hev-long-sunnypilot-port.md` with the human driver present.

This is a personal fork change. Do not open an upstream PR against sunnypilot or commaai.
