# Port Status - Sonata LF Hybrid longitudinal on sunnypilot

**Branch:** `sonata-lf-hev-long-sp`
**Base commit:** `ffa13083` (sunnypilot/opendbc master)
**Implementation HEAD:** `1cf8c8cb`

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

- `opendbc.safety.tests.test_hyundai`: 1,931 tests passed, 208 skipped.
- `opendbc/safety/tests/test.sh`: 8,414 tests passed, 911 skipped; checked C files reached 100% line coverage.
- Hyundai car tests: 13 passed, 2 skipped.
- Route, platform config, Sonata interface, and lateral-limit focused tests: 5 passed.
- Target Python files pass `ruff`; the replay script also passes `py_compile` and `ty check`.
- Empty-fingerprint CarParams checks confirm standard Hyundai safety, LONG boundary behavior, HYBRID_GAS and ALT_STANDSTILL, with ESCC/NON_SCC off.
- `carcontroller.py`, `hyundaican.py`, and `carstate.py` remain zero-diff.

This checkout has no standalone `SConstruct`, so the stale `scons -j8 opendbc/safety` command is not an available entrypoint. Safety tests compile `libsafety.so` directly with `cc`; both targeted and full coverage gates passed through that repository-native path.

## Deferred Gates

- Task 6 route replay is deferred because the three owner rlog files are absent on this machine:
  `~/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--{0,2,3}--rlog.zst`
- Task 7 device deployment, panda rebuild/reflash, radar-disable confirmation, and on-car validation remain manual and safety-critical.

## Resume

1. Provide the three rlog files and run:
   `uv run --with zstandard python opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py <segment-0> <segment-2> <segment-3>`
2. Require the final line `ALL OFFLINE CHECKS PASSED` before device deployment.
3. Perform Task 7 from `2026-07-10-sonata-lf-hev-long-sunnypilot-port.md` with the human driver present.

This is a personal fork change. Do not open an upstream PR against sunnypilot or commaai.
