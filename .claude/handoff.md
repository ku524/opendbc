# Handoff - Sonata LF Hybrid longitudinal sunnypilot port

## Done

- Tasks 1-6 are implemented and committed on `sonata-lf-hev-long-sp`.
- Task 4 platform registration and MAIN safety-param wiring are in `6aefd30d`.
- Task 5 safety tests are in `92116d81`; adversarial follow-up adds ALT-off, TCS13 counter, SCC11/SCC12, and SP-reset coverage.
- Task 6 replay script is in `1cf8c8cb`; adversarial follow-up pins canonical SHA-256, decodes authenticated snapshots, validates timeline/address/TCS13 integrity, and adds 23 replay regression tests.
- Review hardening is committed as `e68ba8dff71803403454046902f4ccb1542f7956`.
- Lifecycle cleanup and additional negative coverage are committed as `89a50b75b2a7bae49f905abfdf9cbf8e69efb3fe`.
- Exception-safe PandaRunner cleanup is committed as `6d6bf2c51c0cc91380554765aa6e2031b08ba4c1`.
- Partial-init and diagnostic-cleanup fault coverage is committed as `15ad0815eb1dd1895f0b3584e0cddf7dbc4dc0aa`.

## Verification

All results below were rerun from `15ad0815eb1dd1895f0b3584e0cddf7dbc4dc0aa`:

- Hyundai safety: 1,938 passed, 208 skipped.
- Full safety gate: 8,421 passed, 911 skipped; 100% checked C line coverage.
- Hyundai car tests: 14 passed, 2 skipped.
- Focused route/config/interface/lateral tests: 5 passed.
- Replay fail-closed tests, lint, compile, and type check passed.
- Replay regression tests: 23 passed; car-interface tests: 267 passed; PandaRunner lifecycle tests: 9 passed.
- LF Hybrid deinit emits the radar enable request with the recorded SP flags; ESCC skips radar cleanup. PandaRunner independently attempts diagnostic mode, deinit, no-output, and reset on failures without masking the primary exception.
- Canonical 0/2/3 replay passed: 18,121 CAN events; 9,065 valid TCS13 frames; stopped 98.26%, moving 100%.
- Community support metadata renders correctly; the unsupported MANDO radar claim was withdrawn.
- Actuation files are zero-diff.

## Deferred

- Task 7 is manual device/on-car work and was intentionally not attempted.

## Next Steps

1. Follow Task 7 exactly, including panda firmware verification and the 0x7D0 radar-disable abort gate.
