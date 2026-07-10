# Handoff - Sonata LF Hybrid longitudinal sunnypilot port

## Done

- Tasks 1-6 are implemented and committed on `sonata-lf-hev-long-sp`.
- Task 4 platform registration and MAIN safety-param wiring are in `6aefd30d`.
- Task 5 safety tests are in `92116d81`; adversarial follow-up adds ALT-off, TCS13 counter, SCC11/SCC12, and SP-reset coverage.
- Task 6 replay script is in `1cf8c8cb`; adversarial follow-up pins canonical SHA-256, decodes authenticated snapshots, validates timeline/address/TCS13 integrity, and adds 22 replay regression tests.
- Review hardening is committed as `e68ba8dff71803403454046902f4ccb1542f7956`.

## Verification

All results below were rerun from `e68ba8dff71803403454046902f4ccb1542f7956`:

- Hyundai safety: 1,935 passed, 208 skipped.
- Full safety gate: 8,418 passed, 911 skipped; 100% checked C line coverage.
- Hyundai car tests: 14 passed, 2 skipped.
- Focused route/config/interface/lateral tests: 5 passed.
- Replay fail-closed tests, lint, compile, and type check passed.
- Canonical 0/2/3 replay passed: 18,121 CAN events; 9,065 valid TCS13 frames; stopped 98.26%, moving 100%.
- Community support metadata renders correctly; the unsupported MANDO radar claim was withdrawn.
- Actuation files are zero-diff.

## Deferred

- Task 7 is manual device/on-car work and was intentionally not attempted.

## Next Steps

1. Follow Task 7 exactly, including panda firmware verification and the 0x7D0 radar-disable abort gate.
