# Sonata LF Hybrid Longitudinal Device Handoff

## Outcome

Required device evidence and every recoverable device-only change were copied to the laptop on 2026-07-11. No further comma device operation is required for the at-home analysis.

The deployed opendbc source is reproducible from local branch `sonata-lf-hev-long-sp-device-b971` at `f62fb8fe18d24c06c08755cab966d86b8b94e37d`. The active `radard.py` change is preserved, but its necessity is not established and it must not be folded into the opendbc PR.

## Current Device State at Handoff

- Device: comma 3X at `10.237.19.156`
- sunnypilot checkout: `staging` at `3781e253cf8c2acf44d64597a1f3a34eff3db992`, with deployed files intentionally dirty
- opendbc symlink: `/data/openpilot/opendbc` -> `opendbc_repo/opendbc`
- detected car: `HYUNDAI_SONATA_LF_HYBRID`
- CarParams: `alphaLongitudinalAvailable=true`, `openpilotLongitudinalControl=true`, `pcmCruise=false`
- handoff-time Params: `AlphaLongitudinalEnabled=1`, `OffroadMode=1`, `IsOffroad=1`, `ExperimentalMode=0`
- active panda firmware SHA-256: `095e3486bf09b42a6d26ce40ab6be55fd0115dc8aefd7181a0187bbfcfc585f1`
- active `radard.py` SHA-256: `8dc45dfcea53fdac181d875cd3abc72913b8cbd8d745de7ea3a0aebca572a865`

`OffroadMode=1` is the handoff snapshot after the drive. It does not describe the setting for the whole recorded route.

## Laptop Recovery Artifacts

Root: `/Users/mark.yeon/Documents/work/oss/sunny_opendbc-device-backups`

| Artifact | SHA-256 | Purpose |
|---|---|---|
| `handoff-20260711/route-e4-evidence.tar` | `31e317d1dc0965f1d686afc805b690ae74896b150a9a1dd5c082c58a7d164c14` | Required qlog/rlog evidence |
| `handoff-20260711/active-source.patch` | `29cd9dc42e36dc86d3cdd7dee250669219e2f570af0b2ce4a1be8898d1f6c47c` | Active source delta against device `staging` |
| `handoff-20260711/panda_h7.bin.signed` | `095e3486bf09b42a6d26ce40ab6be55fd0115dc8aefd7181a0187bbfcfc585f1` | Exact active panda firmware |
| `handoff-20260711/CarParams` | `dc1de6f407021576a39e0d62d40a2dfcc8a56932378354c661dc274880fbe92d` | Route-time vehicle configuration evidence |
| `handoff-20260711/CarParamsPersistent` | `dc1de6f407021576a39e0d62d40a2dfcc8a56932378354c661dc274880fbe92d` | Persistent vehicle configuration evidence |
| `sonata-lf-hev-long-sp-device-b971.bundle` | `11c208a368add1e44d375ca7021a226ceb4e4cade0caefd2fbb15b0ecbccf521` | Complete deployed opendbc Git history |
| `opendbc-production-f62fb8fe.tar.gz` | `febc38e344c5d5541555ea8a8d2c9fe9114d35a5e280a8d9aab7b82448099ed7` | Exact production source payload |
| `panda_h7-sonata-lf-hev-long-release.bin.signed` | `095e3486bf09b42a6d26ce40ab6be55fd0115dc8aefd7181a0187bbfcfc585f1` | Release-named copy of active firmware |
| `pre-custom-f62fb8fe-3781e253/active-files.tar.gz` | `207a5f75ce34c07d159261eb5382568a2fcc95ae43125fdbdf0a20fd1bb70467` | Full pre-custom active-file rollback |
| `pre-custom-f62fb8fe-3781e253/dirty.patch` | `20a00fddf4ac13425d0b438ea887418899aca54cd715c5bc1fb11afa89584c19` | Pre-custom dirty state |
| `radard-poll-all-fix/radard.py` | `8dc45dfcea53fdac181d875cd3abc72913b8cbd8d745de7ea3a0aebca572a865` | Active radard candidate |
| `radard-poll-all-fix/radard.py.original` | `927b67f7888f07631901625be4cfc732433dbbfe5a6dc210723b35392fa2f0ad` | Exact radard rollback |

The same handoff subset remains on the device at `/data/sonata-lf-hev-long-handoff-20260711`.

Verification commands:

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc-device-backups/handoff-20260711
shasum -a 256 -c SHA256SUMS
tar -tf /Users/mark.yeon/Documents/work/oss/sunny_opendbc-device-backups/handoff-20260711/route-e4-evidence.tar
git bundle verify /Users/mark.yeon/Documents/work/oss/sunny_opendbc-device-backups/sonata-lf-hev-long-sp-device-b971.bundle
```

The local and device SHA-256 values matched. The tar index read successfully with 62 entries. The Git bundle reported a complete history.

## Preserved Route Evidence

Route: `000000e4--5ae02c8c77`

- Segment 0: initial startup and UDS evidence
- Segment 9: stationary Drive-gear gate
- Segments 17 through 45: complete long road test plus immediately adjacent context
- Each preserved segment contains both `qlog.zst` and `rlog.zst`
- Video was excluded because it is not required for CAN, controls-state, service-validity, or ride-dynamics analysis

## Every Active Device Modification

### opendbc source

The following 12 deployed files exactly match local revision `f62fb8fe`:

1. `opendbc/car/hyundai/values.py`
2. `opendbc/safety/modes/hyundai_common.h`
3. `opendbc/safety/modes/hyundai.h`
4. `opendbc/car/hyundai/fingerprints.py`
5. `opendbc/car/hyundai/interface.py`
6. `opendbc/car/hyundai/hyundaican.py`
7. `opendbc/car/torque_data/substitute.toml`
8. `opendbc/car/interfaces.py`
9. `opendbc/car/panda_runner.py`
10. `opendbc/car/honda/interface.py`
11. `opendbc/car/toyota/interface.py`
12. `opendbc/car/subaru/interface.py`

These implement the `ALT_STANDSTILL` safety bit, TCS13 standstill handling, 0x386 integrity exception, LF Hybrid registration, LKAS HUD preservation, and exception-safe longitudinal ECU cleanup lifecycle.

Local commit chain, oldest first:

```text
71bba071 hyundai: add ALT_STANDSTILL safety flag (sunnypilot port)
604036f2 hyundai/safety: decode ALT_STANDSTILL param (sunnypilot port)
50070ea2 hyundai/safety: relax 0x386 integrity, standstill from TCS13 across all RX branches (sunnypilot port)
0d67b943 feat(plan): complete task 4 - register Sonata LF Hybrid
383e9dbd fix(hyundai): preserve Sonata LF Hybrid LKAS HUD fields
0266f62a fix(hyundai): restore longitudinal ECU cleanup lifecycle
4f7df6ac fix(hyundai): make deployment cleanup exception safe
f62fb8fe feat(plan): complete task 5 - test ALT_STANDSTILL safety
```

The device was file-deployed instead of checking out this branch, so its top-level Git status remains dirty. A normal sunnypilot update can overwrite these files. The branch, bundle, tar, patch, and firmware copies are the recovery sources.

### Panda firmware

`/data/openpilot/panda/board/obj/panda_h7.bin.signed` was rebuilt from the deployed opendbc safety source and auto-reflashed. Its SHA-256 matches both laptop firmware copies. Do not commit the binary to the source PR; rebuild it from the source changes.

### sunnypilot `radard.py`

Active delta:

```diff
-  sm = messaging.SubMaster(['modelV2', 'carState', 'liveTracks'], poll='modelV2')
+  sm = messaging.SubMaster(['modelV2', 'carState', 'liveTracks'])
   while True:
     sm.update()
+    if not sm.updated['modelV2']:
+      continue
```

This makes SubMaster wake for every subscribed service while retaining model-driven radar processing.

Do not merge this into the opendbc PR. It belongs to the main sunnypilot repository and its necessity remains unverified. The observed intermittent `communication issue between processes` followed repeated diagnostic SubMaster subscriptions. Reader slots are limited and were not reclaimed by closing those test subscribers; new subscribers reset or evicted existing readers. The problem stopped after diagnostic subscriptions stopped. Supporting falsifiers:

- Original `radard.py` had already completed a clean 225-second observation.
- Road-test service validity was 100% after diagnostic subscriptions stopped.
- CAN invalid/timeout counts and panda RX invalid/fault counts stayed zero.

Required decision test: clean vehicle boot, no external message subscribers, compare original and candidate `radard.py` under the same drive conditions. Until that A/B closes the loop, preserve the candidate only as a separate main-repo experiment.

### Runtime Params

`AlphaLongitudinalEnabled` and `OffroadMode` were changed through sunnypilot settings during deployment and validation. These are runtime state, not PR source. The copied one-byte snapshots preserve the handoff state.

## Temporary Changes Already Reverted

- `radard-poll-fix`: changed polling to `carState` and gated model processing. It caused intermittent `radarState` invalidity and was reverted. Preserved under `radard-poll-fix/`.
- `selfdrived-readiness-fix`: diagnostic readiness experiment. It did not prevent recurrence and was reverted. Preserved under `selfdrived-readiness-fix/`.
- Repeated diagnostic SubMaster processes: stopped. They were not source edits and must not be restarted during clean validation.

None of these reverted experiments belongs in the personal PR.

## Objective Road-Test Result

Route segments 19 through 43 provide about 25 minutes of raw-CAN driving evidence:

- `ACCEnable=0`: 74,988 of 74,988 observed frames
- stock SCC source 0: zero frames
- openpilot SCC11 and SCC12: 75,002 each at about 50 Hz
- tester-present: 1,500 at about 1 Hz
- no dual-SCC transmission
- panda safety mode Hyundai with parameter 1030; RX invalid 0; faults 0
- service validity: 100% for `carControl`, `carState`, `livePose`, `liveTorqueParameters`, `longitudinalPlan`, `radarState`, and `selfdriveState`
- no CAN invalid/timeout, permanent steering fault, stock AEB, or stock FCW
- 13 standstill episodes; 11 resumed
- 14 longitudinal-active intervals; driver confirmed intermediate disengagements were intentional
- brake endings showed about 2.3 to 2.7 ms qlog-order disengagement latency
- gas override was observed with longitudinal control inactive in 702 of 703 coincident qlog samples; one sample was message ordering

The 17 SCC12 safety rejections occurred 1 to 80 ms before qlog brake/active endings while requested acceleration was still nonzero. This is consistent with panda stopping an outgoing command before the later qlog state transition, not a dual-SCC or CAN-integrity failure.

Subjective review remains: unintended acceleration/braking, stop/resume launch strength, brake/gas override feel, warnings seen, and comfort. The copied route contains the required evidence for correlating those observations at home.

## Safe Rollback

Do not use a comma-only reboot while the vehicle ignition remains on after longitudinal radar disable. That can leave the stock radar ECU disabled until a full vehicle ignition cycle and show `Cruise fault: Restart the car to engage`.

Full rollback procedure:

1. Park, apply parking brake, keep brake held, and disable Alpha Longitudinal in settings.
2. While the device is reachable, stop manager and restore the pre-custom active files:

```bash
ssh comma@10.237.19.156
pkill -INT -f "^python3 ./manager.py$" || true
tar -xzf /data/sonata-lf-hev-long-backup/pre-custom-f62fb8fe-3781e253/active-files.tar.gz -C /data/openpilot
sync
```

3. Turn the vehicle fully off, wait for the comma to power down, then start the vehicle again. This resets the radar ECU and lets `pandad` reconcile firmware from the restored tree.
4. Confirm stock cruise behavior before driving.

Targeted `radard.py` rollback:

```bash
cp /data/sonata-lf-hev-long-backup/pre-radard-poll-all-fix/radard.py /data/openpilot/selfdrive/controls/radard.py
sync
```

Then perform the same full vehicle OFF/ON cycle. The laptop original is `radard-poll-all-fix/radard.py.original`.

## Personal PR Integration Path

1. Treat `sonata-lf-hev-long-sp-device-b971` at `f62fb8fe` as the deployed source truth. The bundle can recreate it if the worktree is lost.
2. Rebase or cherry-pick the eight commits onto the updated personal opendbc branch, resolving upstream changes in source and tests together.
3. Re-run targeted safety, Hyundai interface, lifecycle, and replay tests before updating the personal PR.
4. Exclude `panda_h7.bin.signed`, Params snapshots, route logs, and temporary diagnostic patches from the PR.
5. Handle `radard.py` only in a separate sunnypilot main-repository change after clean A/B evidence proves it is required.

No upstream commaai or sunnypilot PR is intended. This is a personal-fork vehicle port.
