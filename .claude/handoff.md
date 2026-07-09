# Handoff - Sonata LF Hybrid longitudinal sunnypilot port

## Done

- Tasks 1-6 are implemented and committed on `sonata-lf-hev-long-sp`.
- Task 4 platform registration and MAIN safety-param wiring are in `6aefd30d`.
- Task 5 safety tests are in `92116d81`; full safety coverage passed.
- Task 6 replay script is in `1cf8c8cb` with sunnypilot `CarParamsSP`, tuple-update, and apply APIs.

## Verification

- Hyundai safety: 1,931 passed, 208 skipped.
- Full safety gate: 8,414 passed, 911 skipped; 100% checked C line coverage.
- Hyundai car tests: 13 passed, 2 skipped.
- Focused route/config/interface/lateral tests: 5 passed.
- Replay static checks, lint, compile, and type check passed.
- Actuation files are zero-diff.

## Deferred

- Full Task 6 replay cannot run until the three owner rlog segments are copied to this machine.
- Task 7 is manual device/on-car work and was intentionally not attempted.

## Next Steps

1. Run the replay command documented in `PORT-STATUS.md` with the owner segments and require `ALL OFFLINE CHECKS PASSED`.
2. Follow Task 7 exactly, including panda firmware verification and the 0x7D0 radar-disable abort gate.
