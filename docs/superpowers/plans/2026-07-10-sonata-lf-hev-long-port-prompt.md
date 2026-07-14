# Implementation-instruction prompt (paste into a fresh agent session)

This is the exact prompt used to direct an agent through `2026-07-10-sonata-lf-hev-long-sunnypilot-port.md`.
See `PORT-STATUS.md` in this same directory for what is already done vs remaining before pasting this.

**Cross-machine note:** the prompt below references `/Users/mark.yeon/Documents/work/oss/opendbc` (the comma-side
reference repo) as read-only source. If that path does not exist on this machine, use
`reference-comma-sonata-lf-hev-long.diff` (bundled in this same directory) instead — it is the identical diff
exported to a patch file — and `2026-07-10-sonata-lf-hev-longitudinal.md` (bundled here too) for the verbatim
test-class / replay-script source text referenced in Tasks 5-6.

---

Port the "Sonata LF Hybrid openpilot longitudinal" change onto sunnypilot's opendbc fork by executing this plan:
  /Users/mark.yeon/Documents/work/oss/sunny_opendbc/docs/superpowers/plans/2026-07-10-sonata-lf-hev-long-sunnypilot-port.md

TWO-REPO SETUP (read carefully):
- WORK IN (edit + verify + commit here): /Users/mark.yeon/Documents/work/oss/sunny_opendbc   <-- sunnypilot's opendbc fork. This is your working tree.
- READ-ONLY REFERENCE (do NOT edit): /Users/mark.yeon/Documents/work/oss/opendbc  branch `sonata-lf-hev-long`. This holds the exact tested diff to mirror. Fetch verbatim text with `git -C /Users/mark.yeon/Documents/work/oss/opendbc show sonata-lf-hev-long:<path>` and view hunks with `git -C /Users/mark.yeon/Documents/work/oss/opendbc diff master...sonata-lf-hev-long -- <path>`. If this path does not exist on this machine, use the bundled `docs/superpowers/plans/reference-comma-sonata-lf-hev-long.diff` and `2026-07-10-sonata-lf-hev-longitudinal.md` in the sunny_opendbc repo instead (same content).

This is a PORT of a fully tested change, NOT a fresh implementation, and it is a PERSONAL FORK (no upstream PR). Follow the plan task-by-task (Task 0 -> 6), TDD, one commit per task, using the superpowers:executing-plans skill. Scope for THIS run = Tasks 0-6 (all offline, in sunny_opendbc). Task 7 (on-device deploy + on-car drive) is a separate manual step the human drives — do NOT attempt it.

BEFORE STARTING: read `docs/superpowers/plans/PORT-STATUS.md` in sunny_opendbc — some tasks (currently Task 1, 2, 3) may already be committed on branch `sonata-lf-hev-long-sp`. Check `git log --oneline` and diff against the plan before redoing completed work.

METHOD
- Env: `cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc && source setup.sh` (or `uv run` prefixes). Build panda safety with `scons -j8 opendbc/safety` before safety tests.
- Run each task's verification command and SHOW the actual output before moving on. Never claim a step passed without pasting output.

NON-NEGOTIABLE CONSTRAINTS (the adversarial review + route data pinned each of these)
1. Edit ONLY in sunny_opendbc. The comma repo (or bundled diff) is the read-only source of truth — never modify it.
2. `ALT_STANDSTILL = 1024` goes in the MAIN `HyundaiSafetyFlags` (values.py) and MAIN `param` decode (hyundai_common.h). The interface OR-in MUST target `ret.safetyConfigs[-1].safetyParam` inside `_get_params` — NEVER `ret.safetyParam` / `_get_params_sp` (sunnypilot's SP space, where 1024 is meaningless -> car faults 0x386 and never engages).
3. `HYUNDAI_COMMON_RX_CHECKS` becomes 2-param `(whl_legacy, tcs13_legacy)`. sunnypilot has ~16 call sites (not 6). Update EVERY one: the legacy-mode array -> `(true, true)`; all other ~15 -> `(false, false)`. Missing one = compile break. Verify with `grep -nE "HYUNDAI_COMMON_RX_CHECKS\((true|false)\)"` returning nothing.
4. Add the alt_standstill RX array in BOTH the longitudinal branch AND the non-long radar-SCC branch, with `if (hyundai_alt_standstill)` as the OUTERMOST FIRST condition of each selection (it must win over the fcev/lda/non_scc nesting). The non-long array must mirror its sibling `hyundai_rx_checks` exactly, INCLUDING `HYUNDAI_SCC12_ADDR_CHECK(0)` and `HYUNDAI_SCC11_ADDR_CHECK(0)`. Only 0x386 is relaxed; 0x394/TCS13 stays strict (tcs13_legacy = false everywhere).
5. vehicle_moving: gate the 0x386 block with `&& !hyundai_alt_standstill`, and in the 0x394 block add `if (hyundai_alt_standstill) { vehicle_moving = !GET_BIT(msg, 47U); }` (StandStill bit47, 1=stopped — polarity verified on the owner route).
6. Do NOT add `0x2AB` (ESCC) or `0x391` (LDA button) to the fingerprint — both verified ABSENT on the route; adding them trips sunnypilot's ENHANCED_SCC / HAS_LDA_BUTTON auto-flags and diverges the safety config.
7. New platform flags = `HyundaiFlags.HYBRID` ONLY. No LEGACY, no UNSUPPORTED_LONGITUDINAL, no TCU_GEARS. Use `HyundaiPlatformConfig` (keeps NON_SCC dormant).
8. HAND-EDIT (literal patch will fail — different wrapping in sunnypilot): the `STEER_MAX = 255` tuple in values.py and the `no_eps_platforms` set in tests/test_hyundai.py. Insert the token in place.
9. `carcontroller.py` / `hyundaican.py` / `carstate.py` must stay ZERO-DIFF (all flag-driven). Prove with `git diff --stat` at the end.
10. Copy the test class (`TestHyundaiLongitudinalSafetyAltStandstill`) and the replay script VERBATIM from the reference branch (or the bundled `2026-07-10-sonata-lf-hev-longitudinal.md`), then adapt only import lines if sunnypilot's car_helpers API differs.
11. Line numbers in the plan are anchors from sunnypilot commit b9712d2 — match by quoted content, not line number.

FIRST-STEP SANITY CHECKS (Task 1 Step 1 / Task 4): confirm in sunny_opendbc that (a) `HyundaiSafetyFlags` ends at `ALT_LIMITS_2 = 512` so 1024 is free, (b) `CAR.HYUNDAI_SONATA_LF` exists as the specs base and `CAR.HYUNDAI_SONATA_LF_HYBRID` does not already exist. If either differs, STOP and report before editing.

VERIFICATION GATES (must all be green)
- `scons -j8 opendbc/safety` compiles.
- `python -m unittest opendbc.safety.tests.test_hyundai` full suite passes (incl. the new `TestHyundaiLongitudinalSafetyAltStandstill`).
- `./opendbc/safety/tests/test.sh` passes (MISRA + 100% C line coverage) — or sunnypilot's documented safety-test entrypoint.
- `python -m pytest opendbc/car/hyundai/tests/test_hyundai.py -q` passes.
- `uv run --with zstandard python opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py` prints "ALL OFFLINE CHECKS PASSED". (Requires the owner's 3 local route segments — see the companion plan's Prerequisites; if absent on this machine, this gate is deferred, say so explicitly.)

STOP CONDITIONS
- Same test fails twice for the same reason -> STOP, report state + hypotheses; do not guess-patch in a loop.
- If `get_params(...)` with an empty fingerprint unexpectedly enables ESCC/NON_SCC, or 1024 collides in sunnypilot -> STOP and report (fork divergence beyond the plan's assumptions).

DONE = Tasks 0-6 committed on branch `sonata-lf-hev-long-sp` in sunny_opendbc, all five verification gates green, actuation files zero-diff. Report the final `git -C /Users/mark.yeon/Documents/work/oss/sunny_opendbc log --oneline` and the `git diff --stat` vs the base commit.
