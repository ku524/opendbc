# Port Status — Sonata LF Hybrid longitudinal on sunnypilot

**Branch:** `sonata-lf-hev-long-sp`
**Base commit:** `ffa13083` (sunnypilot/opendbc master, "Nissan Leaf: fix cancel button via CRUISE_THROTTLE forwarding")
**HEAD as of this note:** `418995e7`

## Done (committed)

| Plan task | Commit | What |
|---|---|---|
| Task 1 | `c63a1158` | `HyundaiSafetyFlags.ALT_STANDSTILL = 1024` added in `values.py` |
| Task 2 | `e2ab5806` | `HYUNDAI_PARAM_ALT_STANDSTILL` decoded in `hyundai_common.h` (new global `hyundai_alt_standstill`) |
| Task 3 | `418995e7` | `HYUNDAI_COMMON_RX_CHECKS` split to 2-param across all ~16 call sites in `hyundai.h`; new `alt_standstill` RX arrays added in BOTH the longitudinal branch and the non-long radar-SCC branch; `vehicle_moving` sourced from TCS13 `StandStill` under the flag |

**Not yet independently verified on this machine:** Tasks 1-3 have not been through `scons -j8 opendbc/safety` + the hyundai safety test suite in this session (no ARM/host build toolchain was available when this checkpoint was made). **Run Task 3 Steps 6-7 of the port plan (build + regression test) before proceeding to Task 4**, to catch any compile issue in the 16-site refactor before building further on top of it.

## Remaining (not started)

- **Task 4** — register `CAR.HYUNDAI_SONATA_LF_HYBRID` platform, wire `ALT_STANDSTILL` into `interface.py`'s `_get_params` (NOT `_get_params_sp`), fingerprints, torque substitute, test route, no_eps_platforms. Zero-diff proof for carcontroller/hyundaican/carstate.
- **Task 5** — port the `TestHyundaiLongitudinalSafetyAltStandstill` safety test class.
- **Task 6** — port the offline replay script (`replay_sonata_lf_hybrid_long.py`); requires the owner's 3 local rlog segments (see paths in the companion plan's Prerequisites — these live on the original machine under `~/Downloads/`; copy them over if resuming elsewhere and running this gate).
- **Task 7** — on-device deploy (manual, human-driven; not part of any agent run).

## How to resume on another machine

1. Clone/pull this repo (personal fork remote, see below) and check out `sonata-lf-hev-long-sp`.
2. Read this file, then `git log --oneline` to confirm it matches the table above.
3. Open `2026-07-10-sonata-lf-hev-long-sunnypilot-port.md` in this same directory — that is the plan.
4. Either paste `2026-07-10-sonata-lf-hev-long-port-prompt.md` into a fresh agent session (it already tells the agent to check this status file first), or continue manually from Task 3 Steps 6-7 (build+verify what's already committed) and then Task 4.
5. The read-only comma-side reference repo (`/Users/mark.yeon/Documents/work/oss/opendbc`) will likely NOT exist on a new machine. Use `reference-comma-sonata-lf-hev-long.diff` (full diff, bundled in this directory) and `2026-07-10-sonata-lf-hev-longitudinal.md` (the original comma-side plan with the verbatim test class + replay script text, also bundled here) instead — same content, self-contained.
6. Owner's route segments (needed only for Task 6 / replay verification), originally at:
   `~/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--{0,2,3}--rlog.zst`
   These are NOT bundled in this repo (large binary route data) — copy them separately if you need to run Task 6's replay gate on the new machine.

## Key facts to keep in mind (see the plans for full detail)

- This is a **personal fork** change — never open a PR upstream (sunnypilot or comma).
- The whole point of `ALT_STANDSTILL` is that this car's WHL_SPD11 (0x386) has no valid counter/checksum; the flag relaxes only that message and re-sources standstill detection from TCS13 (0x394), which does have integrity.
- `0x2AB` (ESCC) and `0x391` (LDA button) are verified ABSENT on the owner's route — do not add them to the fingerprint, or sunnypilot's auto-detect flags will diverge the safety config from what's been analyzed.
- On-car, the one thing that cannot be verified offline is whether this car's radar accepts the 0x7D0 communication-control disable. That's Task 7 territory.
