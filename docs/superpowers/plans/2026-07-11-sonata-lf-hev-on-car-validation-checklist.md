# Sonata LF Hybrid Follow-Up On-Car Validation Checklist

## Purpose

Validate the pushed `sonata-lf-hev-long-sp` candidate on the original Sonata LF Hybrid from a different laptop. The candidate includes smoother start/stop behavior, `MANDO_RADAR`, and `steerRatio=16.4`.

This is a manual vehicle test. The driver remains responsible for control. Factory AEB may be unavailable whenever sunnypilot longitudinal control disables the stock radar ECU.

## Source of Truth

- Personal fork: `ku524/opendbc`
- Branch: `sonata-lf-hev-long-sp`
- Draft PR: `https://github.com/ku524/opendbc/pull/1`
- Core follow-up code commit: `bc54535e`
- Device and rollback record: `2026-07-11-sonata-lf-hev-long-device-handoff.md`
- Laptop bootstrap prompt: `2026-07-10-sonata-lf-hev-long-laptop-deployment-prompt.md`

On the new laptop, fetch the branch and record its current remote HEAD. Do not assume the short commit above is the branch tip because documentation commits may follow it.

## 1. New-Laptop Preparation

- Read `AGENTS.md`, `.claude/handoff.md`, `PORT-STATUS.md`, this checklist, and the device handoff before contacting the comma.
- Clone or fetch the personal fork and check out `sonata-lf-hev-long-sp`.
- Confirm a clean worktree and that `bc54535e` is an ancestor of `HEAD`.
- Locate the separately preserved device-backup directory. Verify its `SHA256SUMS` and Git bundle before relying on it.
- Keep route logs, Params, firmware binaries, and device backups outside Git.
- Record the laptop, sunnypilot, opendbc, and branch revisions used for the session.

Suggested source checks:

```bash
git fetch origin sonata-lf-hev-long-sp
git switch --detach origin/sonata-lf-hev-long-sp
git status --short --branch
git log -1 --oneline
git merge-base --is-ancestor bc54535e HEAD
```

## 2. Pre-Deployment Safety Record

Before changing the device:

- Park, apply the parking brake, and keep the vehicle offroad.
- Record the active sunnypilot branch/commit, `opendbc_repo` branch/commit/dirty state, opendbc symlink target, panda firmware hash, and relevant `pandad` logs.
- Back up every active file that deployment may replace. Preserve dirty changes instead of overwriting them.
- Confirm the exact rollback archive and original `radard.py` are readable.
- Do not create temporary `SubMaster`, `SubSocket`, or repeated live-monitor subscribers. Analyze qlog/rlog only after the route ends.

Stop if any source revision, backup, or rollback input is missing or unreadable.

## 3. Isolate the PR Candidate

The prior drive used an unproven main-repository `radard.py` polling candidate. It is not part of this opendbc branch.

1. Restore the original `radard.py` from the verified backup.
2. Deploy the fetched opendbc branch using the build path found in the checked-out sunnypilot source. Do not guess build or flash commands.
3. Record the resulting opendbc revision and panda firmware hash.
4. Perform a full vehicle OFF/ON cycle. A comma-only reboot does not reliably re-enable the stock radar ECU.
5. Verify the original `radard.py` remains active after boot.

Stop for user approval immediately before reboot, panda flash or auto-reflash, Alpha Longitudinal enablement, and actual vehicle actuation.

## 4. sunnypilot Settings

While offroad, enable sunnypilot Longitudinal Control (Alpha), then open the Hyundai/Kia/Genesis vehicle settings and select:

- `Custom Longitudinal Tuning`: `Dynamic`
- `Experimental Mode`: off for the first comparison
- Map, vision-curve, and speed-limit longitudinal modifiers: off for the first comparison

The UI stores `Dynamic` as `HyundaiLongitudinalTuning=1`. The selector is disabled while onroad or while sunnypilot longitudinal control is disabled.

Record every setting before each route. Do not infer a setting from a previous route or from the handoff snapshot.

For attribution, use this order if conditions allow matched safe runs:

1. PR-only candidate with original `radard.py` and tuning `Off`.
2. Same source and route class with tuning `Dynamic`.

Do not change source, `radard.py`, driving personality, or experimental modifiers between those two runs.

## 5. Static and Ignition Gates

Confirm from stored Params and existing process logs:

- Fingerprint is `HYUNDAI_SONATA_LF_HYBRID`.
- `openpilotLongitudinalControl=true`, `pcmCruise=false`, and `radarUnavailable=false`.
- Hyundai safety parameters retain LONG, HYBRID, and ALT_STANDSTILL.
- The candidate reports `steerRatio=16.4` and enables `MANDO_RADAR`.
- CAN is valid with no timeout, panda RX invalid count, or panda fault.
- Radar ECU `0x7D0` normal communication is disabled after engagement setup.
- Stock SCC source-0 frames stop, openpilot SCC11/SCC12 transmit near 50 Hz, tester-present remains near 1 Hz, and dual SCC is absent.
- Mando bus-1 tracks `0x500-0x51f` remain present near 20 Hz.
- No EPS, LKAS, HUD, cruise, radar, or communication warning appears.

Stop and roll back on an empty route, missing CarParams, wrong fingerprint or safety parameter, radar unavailability, CAN invalid/timeout, stock SCC persistence, dual SCC, radar-disable failure, or any warning.

## 6. Staged Driving Checks

Use a closed or low-risk area first, remain ready to brake, and keep the first actuation at minimum speed.

### Stage A: Overrides and basic actuation

- Engage at low speed behind clear road space.
- Confirm brake disengagement and gas override are immediate.
- Confirm cancel and re-engagement work.
- Abort on unintended acceleration, braking, delayed override, or warning.

### Stage B: Standstill and ride quality

- Test several lead-following stops, complete hold, and resume events.
- Include gentle and moderate lead departures without forcing unsafe scenarios.
- Rate launch force, low-speed surge, final-stop jerk, following-distance stability, and oscillation.
- Compare matched `Off` and `Dynamic` runs when practical.

### Stage C: Mando lead selection

- Test a stable same-lane lead at several gaps.
- Observe adjacent-lane vehicles, curves, lead cut-ins/cut-outs, stopped traffic, and roadside objects.
- Abort on phantom braking, failure to track an obvious same-lane lead, persistent adjacent-lane selection, or unstable lead switching.

### Stage D: Steering ratio

- Use legal speeds over gentle left and right curves, preferably spanning 40-100 km/h.
- Check centering, path tracking, left/right symmetry, oscillation, and steering torque saturation.
- Do not adjust lateral torque limits during this validation.

## 7. Evidence to Preserve

For every run, record:

- Exact source commits, panda firmware hash, active `radard.py` hash, and all longitudinal settings.
- Route identifier, segment range, start/end time, road class, and weather/traffic notes.
- Driver annotations for engagement, override, standstill, resume, harsh launch/stop, cut-in, false lead, and steering anomaly.
- Complete rlogs required for offline CAN, `radarState`, `longitudinalPlan`, `carState`, `selfdriveState`, and steering analysis.
- Any warning screenshot and the corresponding route timestamp.

Do not use a route touched by repeated diagnostic subscribers as safety or validity evidence. After suspected reader eviction, stop all monitors, perform a full vehicle OFF/ON cycle, and collect a new route.

## 8. Acceptance Criteria

- No unintended acceleration/braking and no vehicle or comma fault.
- Brake, gas, and cancel overrides remain immediate.
- Standstill hold and resume remain reliable.
- Launch and final-stop comfort materially improve without delayed response or excessive following gaps.
- CAN and panda remain valid; stock SCC and dual SCC remain absent.
- Physical lead selection is stable with no safety-relevant phantom braking.
- `steerRatio=16.4` produces stable, symmetric tracking without new oscillation or saturation.
- Original-`radard.py` PR-only run completes cleanly, establishing that the separate polling patch is unnecessary. If it fails, preserve evidence and investigate before changing runtime polling.

## 9. Rollback

On any abort condition:

1. Park, apply the parking brake, hold the brake, and disable Alpha Longitudinal.
2. Stop manager and restore the verified pre-custom active files described in the device handoff.
3. Sync storage and turn the vehicle fully off.
4. Wait for the comma to power down, then restart the vehicle.
5. Confirm stock cruise and stock radar behavior before driving.

Do not use a comma-only reboot as the rollback ignition cycle.
