# Handoff - Sonata LF Hybrid longitudinal sunnypilot port

## Done

- Tasks 1-6 are implemented and committed on `sonata-lf-hev-long-sp`.
- Task 4 platform registration and MAIN safety-param wiring are in `6aefd30d`.
- Task 5 safety tests are in `92116d81`; adversarial follow-up adds ALT-off, TCS13 counter, SCC11/SCC12, and SP-reset coverage.
- Task 6 replay script is in `1cf8c8cb`; adversarial follow-up makes it fail closed and adds 9 replay regression tests.

## Verification

- Hyundai safety: 1,934 passed, 208 skipped.
- Full safety gate: 8,417 passed, 911 skipped; 100% checked C line coverage.
- Hyundai car tests: 14 passed, 2 skipped.
- Focused route/config/interface/lateral tests: 5 passed.
- Replay fail-closed tests, lint, compile, and type check passed.
- Community support metadata renders correctly; the unsupported MANDO radar claim was withdrawn.
- Actuation files are zero-diff.

## Deferred

- Full Task 6 replay cannot run until the three owner rlog segments are copied to this machine. Their SHA-256 values are unavailable, so cryptographic route identity remains unverified.
- Task 7 is manual device/on-car work and was intentionally not attempted.

## Next Steps

1. Run the replay command documented in `PORT-STATUS.md` with the owner segments and require `ALL OFFLINE CHECKS PASSED`.
2. Follow Task 7 exactly, including panda firmware verification and the 0x7D0 radar-disable abort gate.
