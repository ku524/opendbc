# Sonata LF Hybrid Longitudinal — Port to sunnypilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to execute task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Re-apply the tested "Sonata LF Hybrid openpilot longitudinal" change (from the comma-opendbc reference branch `sonata-lf-hev-long`) onto **sunnypilot's own opendbc fork**, then deploy to the on-car comma device.

**Architecture:** This is a PORT, not a fresh implementation. The reference change is fully committed and offline-verified on comma-opendbc master (see companion plan `2026-07-10-sonata-lf-hev-longitudinal.md`). sunnypilot's opendbc fork diverges (MADS, ESCC/non-SCC, a separate "sp" safety-param space, and ~16 `HYUNDAI_COMMON_RX_CHECKS` call sites vs comma's 6). The semantic change is identical; only the insertion points, the call-site count, and two runtime auto-detect flags differ. A literal `git apply` of the comma-master hunks will FAIL on several files — every edit below is hand-applied and content-anchored.

**Tech Stack:** Python 3.12 (opendbc car layer), C (panda safety), scons (panda firmware build), capnp/cffi (safety tests). sunnypilot vendors opendbc as its `opendbc_repo` submodule; the panda firmware is compiled FROM `opendbc/safety` on the device.

## Global Constraints

- **Personal fork; NOT for upstream.** Do not open a PR against sunnypilot or commaai.
- **Two working trees:** do all edits + offline verification in the local sunnypilot opendbc clone at `/Users/mark.yeon/Documents/work/oss/sunny_opendbc` (referred to as `$SP`), then deploy the same commits to the device's `opendbc_repo`. Do NOT edit the comma-opendbc repo at `/Users/mark.yeon/Documents/work/oss/opendbc` — that is the read-only reference source. **NOTE (cross-machine resume):** if that comma repo path is unavailable on this machine, use the bundled `docs/superpowers/plans/reference-comma-sonata-lf-hev-long.diff` in THIS repo instead — it is the same diff exported to a patch file.
- **Reference diff = source of truth.** The exact committed change is on the comma reference branch; view it with:
  `git -C /Users/mark.yeon/Documents/work/oss/opendbc diff master...sonata-lf-hev-long -- <path>`
  (or read the equivalent hunk from `reference-comma-sonata-lf-hev-long.diff` in this same `docs/superpowers/plans/` directory).
  Port the *semantics* of that diff, adapted to sunnypilot's structure per each task below.
- **Flag value 1024 is the python↔C contract.** `HyundaiSafetyFlags.ALT_STANDSTILL = 1024` (values.py) and `HYUNDAI_PARAM_ALT_STANDSTILL = 1024` (hyundai_common.h). It lives ONLY in the MAIN `HyundaiSafetyFlags`/`param` space — NEVER in sunnypilot's `HyundaiSafetyFlagsSP` / `current_safety_param_sp`.
- **0x394 (TCS13) stays strict; only 0x386 (WHL_SPD11) is relaxed.** The 2-param macro split is mandatory.
- **ALLOW_DEBUG:** sunnypilot's panda is always a DEBUG build (no release cert), so `hyundai_longitudinal` is un-gated — this port depends on that and it is already satisfied.
- **StandStill polarity is verified** (owner route): bit 47 == 1 = stopped → `vehicle_moving = !GET_BIT(msg, 47U)`.
- **Line numbers below are from sunnypilot opendbc commit `b9712d2`** (device pin). Treat them as anchors; if drifted, match by the quoted content.

## Route-Verified Facts That De-Risk the Port (ground truth — do not re-derive)

Confirmed by replaying the owner's route (`9f9b411a57b8ce21/00000001--d6d081f0e7`) locally:

| Fact | Consequence for the port |
|---|---|
| `0x2AB` (ESCC_MSG) **ABSENT** on bus 0 | sunnypilot ENHANCED_SCC will NOT auto-trigger → safety config matches the tested comma-master path. Do not add 0x2AB to the fingerprint. |
| `0x391` (LDA button) **ABSENT** on bus 0 | `HAS_LDA_BUTTON` stays false → longitudinal branch takes the non-lda `hyundai_long_rx_checks` path → a **single** alt_standstill array suffices (no lda-button variant needed). |
| `0x420` SCC11 + `0x421` SCC12 **PRESENT** on bus 0 | the non-long radar-SCC RX arrays' `SCC11_ADDR_CHECK(0)`+`SCC12_ADDR_CHECK(0)` are satisfied → the ported non-long alt_standstill array must include BOTH. |
| `0x386` no valid counter/checksum; `0x394` valid (brake+StandStill); `0x421` checksum valid; `0x371` gas live; `0x38d` absent (USE_FCA off) | unchanged from the main plan; all confirmed. |

## Sunnypilot Divergences (the whole reason this is a separate port plan)

1. **~16 `HYUNDAI_COMMON_RX_CHECKS(...)` call sites** in `hyundai.h` (comma has 6): the 2-param refactor must touch every one.
2. **Longitudinal branch has a 2-D selection** (fcev × has_lda_button = 4 arrays, `hyundai.h:349-361`) vs comma's 2. Insert the alt_standstill selection as the **outermost first** condition so it wins regardless (safe because LDA is absent for this car).
3. **Non-long radar-SCC arrays carry `SCC12_ADDR_CHECK(0)` AND `SCC11_ADDR_CHECK(0)`** (`hyundai.h:382-383`); comma's had SCC12 only.
4. **`interface.py` has a second method `_get_params_sp`** owning `ret.safetyParam` (the SP space). The ALT_STANDSTILL OR-in goes in `_get_params` on `safetyConfigs[-1].safetyParam` — NOT there.
5. **`values.py` STEER_MAX tuple and `test_hyundai.py` no_eps set are wrapped differently** → literal patch fails, hand-edit.
6. **`carcontroller.py`/`carstate.py` import MADS modules** → not byte-identical to comma, but still need ZERO change for this flag-driven port.
7. sunnypilot extra globals (`hyundai_escc`, `hyundai_non_scc`, `hyundai_longitudinal_main_cruise_toggleable`, `hyundai_has_lda_button`) come from the SP param space; none interact with our MAIN-param flag as long as the car uses `HyundaiPlatformConfig` (not `HyundaiNonSccPlatformConfig`) and its fingerprint omits 0x2AB.

## File Structure (in `$SP`)

- `opendbc/car/hyundai/values.py` — `ALT_STANDSTILL` flag; `CAR.HYUNDAI_SONATA_LF_HYBRID`; STEER_MAX bucket.
- `opendbc/car/hyundai/interface.py` — ALT_STANDSTILL OR-in in `_get_params`.
- `opendbc/car/hyundai/fingerprints.py`, `opendbc/car/torque_data/substitute.toml`, `opendbc/car/tests/routes.py`, `opendbc/car/hyundai/tests/test_hyundai.py` — platform registration.
- `opendbc/safety/modes/hyundai_common.h` — param decode + global bool.
- `opendbc/safety/modes/hyundai.h` — 2-param macro (16 call sites); alt_standstill arrays in BOTH long and non-long branches; vehicle_moving from TCS13.
- `opendbc/safety/tests/test_hyundai.py` — new test class.
- `opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py` — offline replay (copy from reference, fix import paths if needed).
- `opendbc/car/hyundai/tests/test_replay_sonata_lf_hybrid_long.py` — fail-closed replay regression tests.

---

### Task 0: Set up the sunnypilot working branch

**Files:** none (git setup)

- [x] **Step 1: Branch off the device-pinned commit**

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc
git status                      # confirm clean
git rev-parse HEAD              # note the base commit (should be the device pin, e.g. b9712d2 area)
git checkout -b sonata-lf-hev-long-sp
```

- [x] **Step 2: Prime the env**

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc
source setup.sh                 # uv sync + activate .venv (sunnypilot ships this)
```
Expected: venv active, no error. If `setup.sh` differs, use `uv run` prefixes as in later steps.

---

### Task 1: Add `ALT_STANDSTILL` flag (Python) + confirm it is free

**Files:**
- Modify: `$SP/opendbc/car/hyundai/values.py` (`HyundaiSafetyFlags`, after `ALT_LIMITS_2 = 512`)

**Interfaces:**
- Produces: `HyundaiSafetyFlags.ALT_STANDSTILL = 1024`.

- [x] **Step 1: Confirm 1024 is free in sunnypilot's MAIN enum**

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc
rg -n "class HyundaiSafetyFlags" -A 14 opendbc/car/hyundai/values.py
```
Expected: enum ends at `ALT_LIMITS_2 = 512` (identical to comma). If a fork delta already uses 1024 here, STOP and report — pick the next free bit and keep python/C in lockstep.

- [x] **Step 2: Add the member**

After `ALT_LIMITS_2 = 512` in `HyundaiSafetyFlags`:

```python
  ALT_LIMITS_2 = 512
  # Personal fork (Sonata LF Hybrid): car runs standard 'hyundai' safety but WHL_SPD11 (0x386)
  # has no valid counter/checksum. This bit tells the panda safety RX check to skip 0x386 integrity
  # (that message only) and derive vehicle_moving from TCS13 (0x394) StandStill instead.
  # Value MUST match HYUNDAI_PARAM_ALT_STANDSTILL in opendbc/safety/modes/hyundai_common.h.
  ALT_STANDSTILL = 1024
```

- [x] **Step 3: Verify**

```bash
python -c "from opendbc.car.hyundai.values import HyundaiSafetyFlags as F; \
assert F.ALT_STANDSTILL.value==1024; \
assert len([f.value for f in F])==len({f.value for f in F}); print('OK 1024 free')"
```
Expected: `OK 1024 free`

- [x] **Step 4: Commit** — `git add opendbc/car/hyundai/values.py && git commit -m "hyundai: add ALT_STANDSTILL safety flag (sunnypilot port)"`

---

### Task 2: Decode the flag in panda safety (`hyundai_common.h`)

**Files:**
- Modify: `$SP/opendbc/safety/modes/hyundai_common.h`

**Interfaces:**
- Produces: C global `hyundai_alt_standstill`; `HYUNDAI_PARAM_ALT_STANDSTILL = 1024`.

- [x] **Step 1: Add the global** — after `bool hyundai_alt_limits_2 = false;` (~L50):

```c
extern bool hyundai_alt_limits_2;
bool hyundai_alt_limits_2 = false;

extern bool hyundai_alt_standstill;
bool hyundai_alt_standstill = false;
```

- [x] **Step 2: Add the param const** — inside `hyundai_common_init`, after `const uint16_t HYUNDAI_PARAM_ALT_LIMITS_2 = 512;` (~L79):

```c
  const uint16_t HYUNDAI_PARAM_ALT_LIMITS_2 = 512;
  const uint16_t HYUNDAI_PARAM_ALT_STANDSTILL = 1024;
```

- [x] **Step 3: Add the decode** — after `hyundai_alt_limits_2 = GET_FLAG(param, HYUNDAI_PARAM_ALT_LIMITS_2);` (~L87):

```c
  hyundai_alt_limits_2 = GET_FLAG(param, HYUNDAI_PARAM_ALT_LIMITS_2);
  hyundai_alt_standstill = GET_FLAG(param, HYUNDAI_PARAM_ALT_STANDSTILL);
```

> Do NOT touch the SP param block (`hyundai_escc = GET_FLAG(current_safety_param_sp, ...)`). ALT_STANDSTILL is a MAIN-param flag.

- [x] **Step 4: Verify it compiles** (covered by Task 4 build). No standalone commit yet — commit with Task 3 since the two safety files build together. (Or commit now; either is fine.)

---

### Task 3: Panda safety `hyundai.h` — 2-param macro (16 sites) + alt_standstill arrays + vehicle_moving

**Files:**
- Modify: `$SP/opendbc/safety/modes/hyundai.h`
- Test: `$SP/opendbc/safety/tests/test_hyundai.py` (Task 5)

**Interfaces:**
- Consumes: `HYUNDAI_COMMON_RX_CHECKS`, `hyundai_alt_standstill` (Task 2), `GET_BIT` (declarations.h:38, verified present).
- Produces: relaxed-0x386 RX behavior + TCS13 standstill under the flag.

- [x] **Step 1: 2-param macro** — at the `#define HYUNDAI_COMMON_RX_CHECKS(legacy)` (~L41):

Change the signature and the 0x386 / 0x394 lines:
```c
#define HYUNDAI_COMMON_RX_CHECKS(whl_legacy, tcs13_legacy)                  \
  ...
  {.msg = {{0x386, 0, 8, 100U, .ignore_checksum = (whl_legacy), .ignore_counter = (whl_legacy), .max_counter = (whl_legacy) ? 0U : 15U, .ignore_quality_flag = true}, { 0 }, { 0 }}}, \
  {.msg = {{0x394, 0, 8, 100U, .ignore_checksum = (tcs13_legacy), .ignore_counter = (tcs13_legacy), .max_counter = (tcs13_legacy) ? 0U : 7U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  \
  ...
```
(0x260/0x371/0x251/0x4F1 lines unchanged.)

- [x] **Step 2: Update ALL 16 call sites**

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc
grep -n "HYUNDAI_COMMON_RX_CHECKS(" opendbc/safety/modes/hyundai.h
```
Expected: the macro def + 16 calls. Edit each call:
- The **legacy-mode** array (`hyundai_legacy_rx_checks`, ~L480): `HYUNDAI_COMMON_RX_CHECKS(true)` → `HYUNDAI_COMMON_RX_CHECKS(true, true)`.
- **Every other** call (the ~15 sites at approx L330, L334, L339, L344, L372, L381, L387, L394, L401, L409, L413, L418, L423, L429, L434): `HYUNDAI_COMMON_RX_CHECKS(false)` → `HYUNDAI_COMMON_RX_CHECKS(false, false)`.

Then confirm none remain single-arg:
```bash
grep -nE "HYUNDAI_COMMON_RX_CHECKS\((true|false)\)" opendbc/safety/modes/hyundai.h || echo "all two-arg"
```
Expected: `all two-arg`

- [x] **Step 3: Longitudinal-branch alt_standstill array + selection**

In `hyundai_init`, `if (hyundai_longitudinal)` block. The array `hyundai_long_rx_checks` is declared near L329-331; the selection is the if/else at ~L349-361:
```c
    if (hyundai_fcev_gas_signal) {
      if (hyundai_has_lda_button) { SET_RX_CHECKS(hyundai_fcev_lda_button_long_rx_checks, ret); }
      else { SET_RX_CHECKS(hyundai_fcev_long_rx_checks, ret); }
    } else {
      if (hyundai_has_lda_button) { SET_RX_CHECKS(hyundai_lda_button_long_rx_checks, ret); }
      else { SET_RX_CHECKS(hyundai_long_rx_checks, ret); }
    }
```
Add the array next to `hyundai_long_rx_checks`:
```c
    // Personal fork (Sonata LF Hybrid): WHL_SPD11 (0x386) has no valid counter/checksum on this
    // car. Relax 0x386 integrity ONLY (0x394/TCS13 stays strict); vehicle_moving comes from TCS13.
    static RxCheck hyundai_long_alt_standstill_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(true, false)
    };
```
And make `if (hyundai_alt_standstill)` the OUTERMOST first condition of that selection (it wins over fcev/lda; safe because LDA is absent for this car):
```c
    if (hyundai_alt_standstill) {
      SET_RX_CHECKS(hyundai_long_alt_standstill_rx_checks, ret);
    } else if (hyundai_fcev_gas_signal) {
      ...existing fcev/lda nesting unchanged...
    } else {
      ...existing lda nesting unchanged...
    }
```

- [x] **Step 4: Non-long radar-SCC alt_standstill array + selection**

In the non-long `else` branch (the default radar-SCC path, `hyundai_rx_checks` declared ~L381 with `HYUNDAI_SCC12_ADDR_CHECK(0)` + `HYUNDAI_SCC11_ADDR_CHECK(0)`). Add a sibling array that mirrors it exactly but with relaxed 0x386:
```c
    // ALT_STANDSTILL is per-platform, not per-longitudinal-control. Keep lateral-only mode usable
    // when Alpha Long is off by relaxing only WHL_SPD11 (0x386); SCC11/SCC12 and TCS13 stay strict.
    static RxCheck hyundai_alt_standstill_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(true, false)
      HYUNDAI_SCC12_ADDR_CHECK(0)
      HYUNDAI_SCC11_ADDR_CHECK(0)
    };
```
(Match the exact addr-check lines present in the sibling `hyundai_rx_checks` — copy them verbatim; if sunnypilot's default array has only SCC12, include only SCC12. Route confirms SCC11 present, so both is correct if the sibling has both.)
Make `if (hyundai_alt_standstill)` the outermost first condition of the non-long radar-SCC selection, ahead of the fcev/lda/non_scc nesting.

- [x] **Step 5: vehicle_moving from TCS13 in `hyundai_rx_hook`** (~L191-199)

```c
    // sample wheel speed, averaging opposite corners
    if ((msg->addr == 0x386U) && !hyundai_alt_standstill) {
      uint32_t front_left_speed = GET_BYTES(msg, 0, 2) & 0x3FFFU;
      uint32_t rear_right_speed = GET_BYTES(msg, 6, 2) & 0x3FFFU;
      vehicle_moving = (front_left_speed > HYUNDAI_STANDSTILL_THRSLD) || (rear_right_speed > HYUNDAI_STANDSTILL_THRSLD);
    }

    if (msg->addr == 0x394U) {
      brake_pressed = ((msg->data[5] >> 5U) & 0x3U) == 0x2U;
      // Personal fork (Sonata LF Hybrid): 0x386 lacks integrity; TCS13.StandStill (bit 47) is the
      // integrity-valid standstill source. StandStill == 1 means stopped (verified on owner route).
      if (hyundai_alt_standstill) {
        vehicle_moving = !GET_BIT(msg, 47U);
      }
    }
```

- [x] **Step 6: Build the safety** — proves the macro refactor + new arrays compile:

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc && scons -j8 opendbc/safety
```
Expected: clean compile. A compile error = a missed/miswrapped call site (Step 2) or a wrong addr-check macro name (Step 4) — fix and rebuild.

- [x] **Step 7: Regression — existing hyundai safety tests still pass**

```bash
python -m unittest opendbc.safety.tests.test_hyundai -v
```
Expected: same count as before, all `ok`.

- [x] **Step 8: Commit** — `git add opendbc/safety/modes/hyundai.h opendbc/safety/modes/hyundai_common.h && git commit -m "hyundai/safety: ALT_STANDSTILL — relax 0x386, standstill from TCS13 (sunnypilot port)"`

---

### Task 4: Register the platform + wire the safety param (Python)

**Files:**
- Modify: `$SP/opendbc/car/hyundai/values.py`, `interface.py`, `fingerprints.py`, `torque_data/substitute.toml`, `tests/routes.py`, `hyundai/tests/test_hyundai.py`

- [x] **Step 1: Platform config (values.py)** — after the `HYUNDAI_SONATA_LF` entry:

```python
  # Personal fork: LF Hybrid on standard 'hyundai' safety with openpilot longitudinal.
  # Flags = HYBRID only: NO LEGACY, NO UNSUPPORTED_LONGITUDINAL, NO TCU_GEARS (hybrid uses ELECT_GEAR).
  # 0x386 integrity relaxed via HyundaiSafetyFlags.ALT_STANDSTILL set in interface.py.
  # steerRatio 13.27*1.15 mirrors the ICE LF (route-supported); mass ~1595 kg, owner-refinable.
  HYUNDAI_SONATA_LF_HYBRID = HyundaiPlatformConfig(
    [HyundaiCarDocs("Hyundai Sonata Hybrid 2018-19", car_parts=CarParts.common([CarHarness.hyundai_e]),
                    support_type=SupportType.COMMUNITY, support_link="#community")],
    CarSpecs(mass=1595, wheelbase=2.804, steerRatio=13.27 * 1.15),
    flags=HyundaiFlags.HYBRID,
  )
```
First confirm `CAR.HYUNDAI_SONATA_LF` exists as the specs reference and `CAR.HYUNDAI_SONATA_LF_HYBRID` does not already exist:
```bash
rg -n "HYUNDAI_SONATA_LF\b|HYUNDAI_SONATA_LF_HYBRID" opendbc/car/hyundai/values.py
```

- [x] **Step 2: STEER_MAX bucket (values.py) — HAND-EDIT (wrapping differs from comma)**

Add `CAR.HYUNDAI_SONATA_LF_HYBRID` to the `self.STEER_MAX = 255` tuple in place, right after `CAR.HYUNDAI_SONATA_LF`. Do not paste comma's reflowed hunk; insert the token into sunnypilot's existing line layout.

- [x] **Step 3: Safety param OR-in (interface.py) — in `_get_params`, NOT `_get_params_sp`**

After the `if candidate == CAR.KIA_OPTIMA_G4_FL:` override:
```python
    if candidate == CAR.KIA_OPTIMA_G4_FL:
      ret.steerActuatorDelay = 0.2

    # Personal fork: LF Hybrid runs standard 'hyundai' safety but WHL_SPD11 (0x386) lacks a valid
    # counter/checksum. Skip 0x386 integrity and use TCS13 (0x394) StandStill for vehicle_moving.
    if candidate == CAR.HYUNDAI_SONATA_LF_HYBRID:
      ret.safetyConfigs[-1].safetyParam |= HyundaiSafetyFlags.ALT_STANDSTILL.value
```
> CRITICAL: target `ret.safetyConfigs[-1].safetyParam` (MAIN param, same idiom as the LONG/HYBRID_GAS OR-ins). NOT `ret.safetyParam` in `_get_params_sp` (that is the SP space where 1024 has no meaning → car would fault 0x386 and never engage).

- [x] **Step 4: Fingerprint (fingerprints.py)** — add to `FW_VERSIONS` (match sunnypilot's `Ecu` import + dict shape):

```python
  CAR.HYUNDAI_SONATA_LF_HYBRID: {
    (Ecu.fwdRadar, 0x7d0, None): [
      b'\xf1\x00LFhe SCC FNCUP      1.00 1.02 96400-E6500         ',
    ],
    (Ecu.fwdCamera, 0x7c4, None): [
      b'\xf1\x00LFH MFC  AT KOR LHD 1.00 1.01 95740-E6000 171107',
    ],
  },
```
> Do NOT add `0x2AB` (ESCC) or `0x391` (LDA) anywhere — both verified absent; adding them would trip sunnypilot auto-flags.

- [x] **Step 5: Torque substitution (substitute.toml)** — `"HYUNDAI_SONATA_LF_HYBRID" = "HYUNDAI_SONATA_LF"`

- [x] **Step 6: Test route (opendbc/car/tests/routes.py)** — uses `HYUNDAI.` alias:
```python
  CarTestRoute("9f9b411a57b8ce21/00000001--d6d081f0e7", HYUNDAI.HYUNDAI_SONATA_LF_HYBRID),
```

- [x] **Step 7: EPS exclusion (hyundai/tests/test_hyundai.py) — HAND-EDIT (wrapping differs)** — add `CAR.HYUNDAI_SONATA_LF_HYBRID` to the `no_eps_platforms` set literal in place.

- [x] **Step 8: Verify CarParams**

```bash
python -c "
from opendbc.car.hyundai.values import CAR, HyundaiSafetyFlags
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car import structs, gen_empty_fingerprint
CP = CarInterface.get_params(CAR.HYUNDAI_SONATA_LF_HYBRID, gen_empty_fingerprint(), [], alpha_long=True, is_release=False, docs=False)
assert CP.openpilotLongitudinalControl
assert CP.safetyConfigs[-1].safetyModel == structs.CarParams.SafetyModel.hyundai
p = CP.safetyConfigs[-1].safetyParam
for f in (HyundaiSafetyFlags.LONG, HyundaiSafetyFlags.HYBRID_GAS, HyundaiSafetyFlags.ALT_STANDSTILL):
    assert p & f.value, f.name
print('OK: hyundai safety, long ON, ALT_STANDSTILL set')
"
```
Expected: `OK: hyundai safety, long ON, ALT_STANDSTILL set`
(If `get_params` signature differs in sunnypilot, match `opendbc/car/tests/test_models.py`. If `_get_params_sp` unexpectedly flipped ESCC/NON_SCC on with an empty fingerprint, re-check Step 4.)

- [x] **Step 9: Car tests + zero-diff proof**

```bash
python -m pytest opendbc/car/hyundai/tests/test_hyundai.py -q
git diff --stat opendbc/car/hyundai/carcontroller.py opendbc/car/hyundai/hyundaican.py opendbc/car/hyundai/carstate.py
```
Expected: car tests pass; zero diff on the three actuation files.

- [x] **Step 10: Commit** — `git add opendbc/car/hyundai/values.py opendbc/car/hyundai/interface.py opendbc/car/hyundai/fingerprints.py opendbc/car/torque_data/substitute.toml opendbc/car/tests/routes.py opendbc/car/hyundai/tests/test_hyundai.py && git commit -m "hyundai: register Sonata LF Hybrid with openpilot longitudinal (sunnypilot port)"`

---

### Task 5: Safety unit test for the ALT_STANDSTILL path

**Files:**
- Modify: `$SP/opendbc/safety/tests/test_hyundai.py`

- [x] **Step 1: Confirm the base class + helpers exist in sunnypilot**

```bash
rg -n "class TestHyundaiLongitudinalSafety\b|CANPackerSafety|libsafety_py|HyundaiSafetyFlags" opendbc/safety/tests/test_hyundai.py | head
```
Expected: `TestHyundaiLongitudinalSafety`, `CANPackerSafety`, `libsafety_py`, `HyundaiSafetyFlags` all present (sunnypilot mirrors comma here).

- [x] **Step 2: Append the test class** — copy the `TestHyundaiLongitudinalSafetyAltStandstill` class verbatim from the reference branch:
```bash
git -C /Users/mark.yeon/Documents/work/oss/opendbc show sonata-lf-hev-long:opendbc/safety/tests/test_hyundai.py \
  | sed -n '/class TestHyundaiLongitudinalSafetyAltStandstill/,/^$/p'
```
(If the comma repo path is unavailable on this machine, the same class is in `2026-07-10-sonata-lf-hev-longitudinal.md` Task 3 Step 1 of this repo's own `docs/superpowers/plans/` — copy it from there instead.)
Paste it before `if __name__` in `$SP/opendbc/safety/tests/test_hyundai.py`. It sets `HyundaiSafetyFlags.LONG | HYBRID_GAS | ALT_STANDSTILL`, overrides `_user_gas_msg` (E_EMS11), `_user_brake_msg`/`_vehicle_moving_msg` (TCS13), and asserts: 0x386 bad-integrity does not drop controls; TCS13 bad checksum IS rejected; vehicle_moving tracks TCS13.StandStill.

- [x] **Step 3: Run the new class**

```bash
scons -j8 opendbc/safety && python -m unittest opendbc.safety.tests.test_hyundai.TestHyundaiLongitudinalSafetyAltStandstill -v
```
Expected: all `ok`. If `set_safety_hooks` errors, ALT_STANDSTILL isn't decoded → recheck Tasks 2-3.

- [x] **Step 4: Full safety suite + coverage gate**

```bash
python -m unittest opendbc.safety.tests.test_hyundai -v && ./opendbc/safety/tests/test.sh
```
Expected: all pass; `test.sh` MISRA + 100% coverage passes. (If sunnypilot's `test.sh` differs, run its documented safety-test entrypoint; ensure the new C branches are covered.)

- [x] **Step 5: Commit** — `git add opendbc/safety/tests/test_hyundai.py && git commit -m "hyundai/safety: test ALT_STANDSTILL path (sunnypilot port)"`

---

### Task 6: Offline replay against the owner route (in sunnypilot tree)

**Files:**
- Create: `$SP/opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py`

- [x] **Step 1: Copy the reference replay script**

```bash
git -C /Users/mark.yeon/Documents/work/oss/opendbc show \
  sonata-lf-hev-long:opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py \
  > /Users/mark.yeon/Documents/work/oss/sunny_opendbc/opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py
```
(If the comma repo path is unavailable, the full script is in this repo's own `2026-07-10-sonata-lf-hev-longitudinal.md` Task 5 Step 1 — copy it from there instead.)
It reads the 3 local rlog segments, builds the interface with `alpha_long=True`, asserts CarParams (hyundai safety, long ON, LONG|HYBRID_GAS|ALT_STANDSTILL) + parses CarState + re-asserts StandStill polarity.

> **Post-review hardening:** the implemented sunnypilot replay intentionally goes beyond the
> reference script. It uses explicit validation errors rather than `assert`, validates exact
> route filenames and segment set plus canonical SHA-256, decodes the authenticated byte snapshots, validates raw and cross-segment timestamp order, builds the
> fingerprint from recorded CAN, checks unique-timestamp address rates plus edge gaps and forbidden
> auto-flags, validates TCS13 checksum/counter with the host-safety algorithm, and pairs only fresh
> event-order-independent TCS13/WHL_SPD11 samples within each segment.
>
> **Lifecycle hardening (`89a50b75`, `6d6bf2c5`):** base and brand `deinit` APIs carry the recorded `CP_SP`,
> LF Hybrid radar cleanup sends `28 80 01` to `0x7D0` on bus 0 while preserving ESCC gating,
> and `PandaRunner` independently attempts diagnostic safety, deinit, no-output, and reset on
> initialization or exit failures without masking the primary exception.

- [x] **Step 2: Run it** — downloaded the canonical public route segments 0, 2, and 3 from the comma API and ran the validator unchanged.

```bash
cd /Users/mark.yeon/Documents/work/oss/sunny_opendbc
uv run --with zstandard python opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py
```
Observed: `18,121` CAN events replayed, all `9,065` TCS13 frames passed checksum/counter validation,
fresh StandStill pairs were stopped `3044/3098` (`98.26%`) and moving `5031/5031` (`100%`), and the
run ended `ALL OFFLINE CHECKS PASSED`.

- [x] **Step 3: Commit** — `git add opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py && git commit -m "hyundai: offline replay for Sonata LF Hybrid long (sunnypilot port)"`

---

### Task 7: Deploy to the on-car comma device

**Files:** none in-repo (device operations)

**Why it is not source-edit-only:** the Python changes load live, but the panda safety C changes are compiled into the panda firmware and must be recompiled + reflashed. sunnypilot's panda is already an ALLOW_DEBUG build (no release cert), and its firmware is compiled FROM `opendbc/safety` (repo-root symlink `opendbc` → `opendbc_repo/opendbc`), so these edits do land — after a rebuild.

- [ ] **Step 1: Get the branch onto the device's `opendbc_repo`**

Push `sonata-lf-hev-long-sp` to your sunnypilot-opendbc fork remote, SSH to the device (`ssh comma@<device-ip>`), and in `openpilot/opendbc_repo` fetch + checkout that branch. (Or rsync the working tree into `opendbc_repo`.) Confirm the symlink resolves: `readlink openpilot/opendbc` → `opendbc_repo/opendbc`.

- [ ] **Step 2: Rebuild on device (recompiles panda firmware)**

In the openpilot dir on the device, run the build (`scons`, or let `system/manager/build.py` run it on boot). This regenerates `panda/board/obj/panda_h7.bin.signed`.

- [ ] **Step 3: Reboot → auto-reflash → VERIFY**

Reboot. `pandad` detects the firmware signature mismatch and reflashes. **Verify the panda actually took new firmware** (pandad logs / panda firmware git hash). If unchanged, the safety still rejects 0x386 → the car will not engage.

- [ ] **Step 4: Enable Alpha Longitudinal**

In sunnypilot settings, enable the alpha/openpilot longitudinal toggle for this car (`alphaLongitudinalAvailable` is now True).

- [ ] **Step 5: Staged on-car verification (safety-critical)**

Follow `docs/sonata-lf-hev-long-oncar.md` from the reference repo (also bundled in this repo's `docs/superpowers/plans/2026-07-10-sonata-lf-hev-longitudinal.md` Task 6):
1. Empty road, low speed; confirm openpilot ACC engages (not stock cruise).
2. **★ Radar 0x7D0 disable — the only offline-unverifiable gate:** confirm the stock radar stops SCC (no "SCC conditions not met" fight, no dual SCC). If it refuses → ABORT/revert; the car is not viable without it.
3. Standstill hold + resume (TCS13 StandStill path). 4. Driver override (brake→disengage, gas→override). 5. Ride quality.

> Factory AEB is OFF while engaged (radar disabled). Empty road, foot ready to brake, instant-disengage posture.

---

## Self-Review

- **Core safety parity with reference:** values.py, interface.py, fingerprints.py, substitute.toml, routes.py, hyundai_common.h, and hyundai.h preserve the reference safety semantics, including alt_standstill arrays in BOTH long and non-long branches and vehicle_moving from TCS13. Replay validation and Community support metadata deliberately diverge after adversarial review.
- **Divergences handled:** 16 call sites (Task 3 Step 2); 2-D long selection with outermost alt_standstill (Step 3); non-long SCC11+SCC12 (Step 4); `_get_params` not `_get_params_sp` (Task 4 Step 3); hand-edit STEER_MAX + no_eps (Task 4 Steps 2, 7); routes.py alias/path (Step 6).
- **Runtime auto-flags neutralized:** 0x2AB and 0x391 verified absent → no ESCC/LDA divergence; fingerprint deliberately omits them; `HyundaiPlatformConfig` keeps NON_SCC dormant.
- **Placeholder scan:** none — every code step is concrete; commands have expected output; the two lines that "copy from reference" give the exact `git show` to fetch verbatim text.
- **Name/value consistency:** `ALT_STANDSTILL` / `1024` identical in values.py (Task 1), hyundai_common.h (Task 2), interface.py OR-in (Task 4), test (Task 5). Macro `HYUNDAI_COMMON_RX_CHECKS(whl_legacy, tcs13_legacy)` defined Task 3 Step 1, all 16 sites updated Step 2.
- **Owner-refinable, non-blocking:** hybrid `mass`; final `steerRatio` from a highway `liveParameters` capture.
