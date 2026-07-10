# Adversarial Review Prompt: Sonata LF Hybrid Longitudinal Port

You are performing an adversarial, safety-critical code review of the current branch in this repository. Do not edit files, commit, push, or trust prior status reports. Your job is to find defects, unsafe assumptions, untested branches, misleading verification claims, and divergences from the intended port.

## Repository And Scope

- Working tree: `/home/super/work/sunny_opendbc`
- Branch: `sonata-lf-hev-long-sp`
- Base/merge-base: `ffa13083ff80fc88b03a6cbb9b88e887aa090469` (`origin/master`)
- Review HEAD: `6d6bf2c51c0cc91380554765aa6e2031b08ba4c1`
- Primary source diff: `git diff ffa13083ff80fc88b03a6cbb9b88e887aa090469...6d6bf2c51c0cc91380554765aa6e2031b08ba4c1 -- <source paths>`
- Commit series: `git log --oneline --reverse ffa13083ff80fc88b03a6cbb9b88e887aa090469..6d6bf2c51c0cc91380554765aa6e2031b08ba4c1`
- The branch includes large planning/reference documents. Treat them as requirements and leads, not proof that the implementation is correct.

## Read First

1. Applicable `AGENTS.md` and `CLAUDE.md` instructions.
2. `docs/superpowers/plans/2026-07-10-sonata-lf-hev-long-sunnypilot-port.md`
3. `docs/superpowers/plans/reference-comma-sonata-lf-hev-long.diff`
4. `docs/superpowers/plans/PORT-STATUS.md` and `.claude/handoff.md`, while independently verifying every important claim.
5. All changed source and test files under `opendbc/`.
6. Relevant callers, sibling Hyundai safety modes, shared safety initialization, CarInterface base APIs, gear parsing, platform registration, fingerprint matching, and analogous tests.

## Changed Implementation Files

- `opendbc/car/honda/interface.py`
- `opendbc/car/hyundai/fingerprints.py`
- `opendbc/car/hyundai/interface.py`
- `opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py`
- `opendbc/car/hyundai/tests/test_hyundai.py`
- `opendbc/car/hyundai/tests/test_replay_sonata_lf_hybrid_long.py`
- `opendbc/car/hyundai/values.py`
- `opendbc/car/interfaces.py`
- `opendbc/car/panda_runner.py`
- `opendbc/car/subaru/interface.py`
- `opendbc/car/tests/routes.py`
- `opendbc/car/tests/test_car_interfaces.py`
- `opendbc/car/tests/test_panda_runner.py`
- `opendbc/car/torque_data/substitute.toml`
- `opendbc/car/toyota/interface.py`
- `opendbc/safety/modes/hyundai.h`
- `opendbc/safety/modes/hyundai_common.h`
- `opendbc/safety/tests/test_hyundai.py`

## Intended Behavior To Verify, Not Assume

- A new `CAR.HYUNDAI_SONATA_LF_HYBRID` platform uses standard Hyundai safety and `HyundaiFlags.HYBRID` only.
- MAIN Hyundai safety param bit 1024 means `ALT_STANDSTILL`. It must never leak into sunnypilot's separate SP safety-param namespace.
- Only WHL_SPD11 (`0x386`) checksum/counter checks are relaxed for this platform. TCS13 (`0x394`) must retain strict checksum/counter validation.
- `vehicle_moving` comes from TCS13 bit 47 only when `ALT_STANDSTILL` is enabled, with bit 1 meaning stopped.
- The alternate RX configuration must work in both openpilot-longitudinal and lateral-only/radar-SCC modes. It must take precedence over FCEV, LDA-button, ESCC/non-SCC selection and retain every required sibling SCC11/SCC12 check.
- No actuation implementation file should change. Existing flag-driven controller/state behavior must actually support the new platform.
- Empty fingerprints must not accidentally enable ESCC, NON_SCC, or LDA behavior.
- The replay script must conform to this fork's `CarParamsSP`, `update()`, and `apply()` APIs and must fail closed on missing, empty, or unrepresentative route inputs.
- `PandaRunner` initialization and exit failures must attempt deinit, no-output, and panda reset independently without masking an initialization or context-body exception.

## Adversarial Review Checklist

1. Re-derive the Python-to-C flag contract and initialization/reset behavior. Look for stale globals across repeated `set_safety_hooks` calls, integer-width collisions, incorrect enum space, ordering bugs, and cross-mode contamination.
2. Enumerate every `HYUNDAI_COMMON_RX_CHECKS` call site. Confirm exactly which calls use `(true, false)`, `(false, false)`, and `(true, true)`, and whether any generated or preprocessor branch is missed.
3. Trace `hyundai_init` for every relevant combination: LONG on/off, ALT_STANDSTILL on/off, FCEV, HAS_LDA_BUTTON, ESCC, NON_SCC, camera SCC, and legacy. Confirm the new branch selects the correct RX array and preserves all required messages, frequencies, and buses.
4. Trace `hyundai_rx_hook` state updates. Challenge bit numbering, polarity, message integrity ordering, brake interaction, stale `vehicle_moving` state, missing-message behavior, and transitions when safety modes are reinitialized.
5. Trace platform construction through CAR config, DBC lookup, torque substitution, `CarControllerParams`, gear parsing, CarState parsers, interface params, SP params, firmware matching, fuzzy matching, docs, and routes. Do not accept "flag-driven" without following the actual callers.
6. Check whether HYBRID-only flags are sufficient. Attempt to falsify assumptions about ELECT_GEAR versus TCU_GEARS, longitudinal availability, radar-disable address, bus selection, SCC source, harness, mass, steering ratio, steering limits, and firmware identifiers.
7. Review tests for false confidence: inherited tests that do not exercise the intended RX config, counters shared across tests, assertions made before safety validity matters, non-long coverage that never makes the full RX config valid, checksum corruption that could alter the wrong field, coverage exclusions, order dependence, and missing negative controls.
8. Review replay logic for API correctness and measurement validity. Check route ordering, CAN batching and timestamps, parser freshness, missing TCS13/WHL_SPD11 handling, cohort counts, threshold exclusions at exactly 0.3 and 5.0, stale parser values, ratio denominators, `vEgo` bounds, whether `apply()` is meaningful, and whether three segments are sufficient.
9. Verify that `carcontroller.py`, `hyundaican.py`, and `carstate.py` have zero diff, then decide whether zero diff is actually safe for the new platform.
10. Inspect the bundled comma reference diff and identify every semantic hunk that should or should not be present in the sunnypilot port. Explain every divergence.
11. Search for counterexamples in sibling platforms and tests. Do not infer correctness from one route or from the implementation plan.
12. Treat prior test counts, 100% coverage, route facts, and "verified absent" messages as untrusted until reproduced or shown to be unreproducible. Distinguish host `libsafety` compilation/coverage from an actual panda firmware build.

## Verification Expectations

- Run targeted tests first. Run broader relevant tests when feasible.
- This checkout has no standalone `SConstruct`. Determine the repository-native build/test path yourself; do not merely repeat the handoff explanation.
- Owner rlog segments may be absent. If absent, mark route-dependent claims unverified instead of treating replay static checks as route validation.
- Do not perform device deployment or on-car actions.
- Do not output or search for secrets.
- For each suspected defect, attempt a concrete reproduction or falsification before reporting it.
- Separate findings into confirmed, strongly supported, and inferred when evidence strength differs.

## Required Output Format

1. Findings first, ordered Critical, High, Medium, Low. Each finding must include:
   - concise title
   - exact file and line reference
   - concrete failure scenario and safety/user impact
   - evidence or reproduction command and observed result
   - minimal corrective direction
2. Then `Unverified claims / evidence gaps`.
3. Then `Alternative hypotheses checked`, including what evidence falsified or failed to falsify each one.
4. Then `Verification commands run` with exact observed summaries.
5. End with one verdict: `READY`, `READY WITH EXPLICIT DEFERRED GATES`, or `NOT READY`.

Do not provide a generic summary. If no defect is found, say so explicitly, but still list residual risks and missing tests. Do not change the code.
