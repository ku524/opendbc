# Sonata LF Hybrid — openpilot Longitudinal (personal fork) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable openpilot longitudinal (ACC: openpilot controls gas/brake) for the Hyundai Sonata LF Hybrid 2018-19 in a personal opendbc fork, by moving the car onto the standard `hyundai` panda safety mode with a new per-car flag that exempts its integrity-less wheel-speed message from RX checks and sources standstill from an integrity-valid message instead.

**Architecture:** The car is genuinely legacy-class — its WHL_SPD11 (0x386) carries no valid alive-counter or checksum, which is why upstream keeps it on `hyundaiLegacy` safety (which forbids longitudinal). We instead route it to standard `hyundai` safety (which supports longitudinal + has the 0x7D0 radar-disable TX allowlist) and add one new `HyundaiSafetyFlags` bit, `ALT_STANDSTILL` (value 1024), that does exactly two things when set: (1) relaxes only 0x386's RX integrity check while keeping every other message strict, and (2) derives the safety `vehicle_moving` global from TCS13 (0x394) `StandStill` — an integrity-valid message — instead of 0x386 wheel speeds. All longitudinal actuation (SCC12 accel TX, 0x7D0 radar disable, FCA/AEB blocking, hybrid gas/cruise/standstill carstate) is already flag-driven and needs no code change once the car's flags are correct.

**Tech Stack:** Python 3.12 (opendbc car layer), C (panda safety in `opendbc/safety`, compiled to a `libsafety` shared object for unit tests), `uv` for env, `scons` for the safety/panda build, capnp/cffi for tests. openpilot (separate repo) vendors this opendbc via its `opendbc_repo` submodule.

## Global Constraints

- **Personal fork only — NOT for upstream merge.** The change deliberately relaxes a safety integrity check for one car; upstream would reject it. Do not open a PR against commaai/opendbc.
- **Panda must be a non-release / `ALLOW_DEBUG` build.** `hyundai_longitudinal` is gated behind `#ifdef ALLOW_DEBUG` in `hyundai_common.h`; release builds force it `false`. This is the same gate that makes openpilot's "openpilot Longitudinal Control (Alpha)" UI toggle visible, so a non-release openpilot branch satisfies both.
- **Flag value `1024` is the load-bearing python↔C contract.** `HyundaiSafetyFlags.ALT_STANDSTILL = 1024` (python) and `HYUNDAI_PARAM_ALT_STANDSTILL = 1024` (C) MUST be identical. Use the name `ALT_STANDSTILL` on both sides.
- **Do NOT weaken 0x386 globally.** The relaxation must be gated by the new per-car flag only. **0x394 (TCS13) must remain fully integrity-checked** — it is the valid source of both `brake_pressed` and `StandStill`.
- **StandStill polarity is verified** from the owner's route (`9f9b411a57b8ce21/00000001--d6d081f0e7`): bit 47 == 1 means stopped (98.2% at v<0.3 km/h), == 0 means moving (100% at v>5 km/h). Therefore `vehicle_moving = !GET_BIT(msg, 47U)`.
- **100% C line coverage gate.** `opendbc/safety/tests/test.sh` runs `gcovr --fail-under-line=100`. Every new C branch must be exercised by a test.
- **Accepted tradeoff:** factory AEB/FCW is lost when the radar is disabled (this is a radar-SCC car; unavoidable for openpilot longitudinal on this architecture, not specific to this fork).
- **Runtime unknown, out of plan scope (document, do not attempt to automate):** whether the car's radar accepts the 0x7D0 communication-control disable. Only verifiable on-car.

## Verified Route Facts (ground truth — do not re-derive)

Empirically confirmed by replaying the owner's route through `opendbc.car.logreader.LogReader` + `opendbc.can.parser.CANParser`:

| Fact | Evidence |
|---|---|
| 0x386 WHL_SPD11 lacks integrity | alive-counter frozen at 0 across 9064 bus-0 frames; checksum match 2.4% (coincidental) |
| 0x394 TCS13 has integrity | counter cycles 0–7; checksum 100%; carries `DriverOverride` (bits 45-46) + `StandStill` (bit 47) |
| 0x421 SCC12 has integrity | counter + 100% checksum; openpilot's computed SCC12 checksum matches → powertrain will accept openpilot accel |
| All non-legacy RX slots satisfiable | slot (0x260 OR 0x371): 0x371 present (hybrid gas); 0x251, 0x4F1, 0x394, 0x421 all present on bus 0. 0x260 absent (fine, OR'd). |
| StandStill polarity | ==1 stopped 98.2% (v<0.3), ==0 moving 100% (v>5) → `vehicle_moving = !bit47` |
| Radar point frames | Backed-up Alpha Long route has all bus-1 0x500–0x51f tracks at about 20 Hz after SCC normal-communication disable → MANDO_RADAR enabled in follow-up |
| Hybrid gas live | E_EMS11 (0x371) `CR_Vcu_AccPedDep_Pos` has 95 distinct values, 4773 nonzero frames → driver override works |
| 0x38d absent | → `USE_FCA` stays off → AEB-disable goes via SCC12 path (auto-handled) |
| steerRatio | 116-minute highway route supports `16.4`: qualified median `16.402`, left/right `16.405/16.372`, last-20-minute median `16.404` |

## Prerequisites (one-time, not a task)

- Branch `sonata-lf-hev-long` already created off `master`.
- openpilot dev environment with this opendbc fork checked out into openpilot's `opendbc_repo` submodule (for on-car; not needed for the offline tasks below).
- The owner's three route segments present locally:
  - `/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--0--rlog.zst`
  - `.../--2--rlog.zst`
  - `.../--3--rlog.zst`
- opendbc test env: from repo root run `source setup.sh` once (runs `uv sync --all-extras --all-groups`, activates `.venv`). All commands below assume this env (or prefix with `uv run --with zstandard`).

## File Structure

**opendbc car layer (Python):**
- `opendbc/car/hyundai/values.py` — add `HyundaiSafetyFlags.ALT_STANDSTILL`; add `CAR.HYUNDAI_SONATA_LF_HYBRID` platform; add it to the `STEER_MAX = 255` bucket.
- `opendbc/car/hyundai/interface.py` — OR `ALT_STANDSTILL` into `safetyParam` for this car (LOAD-BEARING).
- `opendbc/car/hyundai/fingerprints.py` — `FW_VERSIONS` entry (radar + camera FW).
- `opendbc/car/torque_data/substitute.toml` — map torque data to `HYUNDAI_SONATA_LF`.
- `opendbc/car/tests/routes.py` — add the owner's test route.
- `opendbc/car/hyundai/tests/test_hyundai.py` — add car to `no_eps_platforms`.

**panda safety (C):**
- `opendbc/safety/modes/hyundai_common.h` — decode the new param bit into a new global bool.
- `opendbc/safety/modes/hyundai.h` — 2-param `HYUNDAI_COMMON_RX_CHECKS` macro; new relaxed long RX-check array; `vehicle_moving` from TCS13.
- `opendbc/safety/tests/test_hyundai.py` — new test class `TestHyundaiLongitudinalSafetyAltStandstill`.

**validation + docs:**
- `opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py` — new self-contained offline replay against local route.
- `docs/superpowers/plans/2026-07-10-sonata-lf-hev-longitudinal.md` — this plan.
- `docs/sonata-lf-hev-long-oncar.md` — on-car bring-up checklist + tradeoffs.

---

### Task 1: Add the `ALT_STANDSTILL` safety flag (Python side)

**Files:**
- Modify: `opendbc/car/hyundai/values.py` (`HyundaiSafetyFlags` class, after `ALT_LIMITS_2 = 512`)
- Test: `opendbc/car/hyundai/tests/test_hyundai.py` (existing suite must still pass)

**Interfaces:**
- Produces: `HyundaiSafetyFlags.ALT_STANDSTILL` (IntFlag member, value `1024`). Consumed by Task 3 (C decode must match the value) and Task 4 (interface OR-in).

- [ ] **Step 1: Add the flag member**

In `opendbc/car/hyundai/values.py`, the `HyundaiSafetyFlags(IntFlag)` class currently ends:

```python
  FCEV_GAS = 256
  ALT_LIMITS_2 = 512
```

Change to:

```python
  FCEV_GAS = 256
  ALT_LIMITS_2 = 512
  # Personal fork (Sonata LF Hybrid): car runs standard 'hyundai' safety but WHL_SPD11 (0x386)
  # has no valid counter/checksum. This bit tells the panda safety RX check to skip 0x386 integrity
  # (that message only) and derive vehicle_moving from TCS13 (0x394) StandStill instead.
  # Value MUST match HYUNDAI_PARAM_ALT_STANDSTILL in opendbc/safety/modes/hyundai_common.h.
  ALT_STANDSTILL = 1024
```

- [ ] **Step 2: Verify import + value, no collision**

Run:
```bash
python -c "from opendbc.car.hyundai.values import HyundaiSafetyFlags as F; \
assert F.ALT_STANDSTILL.value == 1024; \
vals=[f.value for f in F]; assert len(vals)==len(set(vals)), 'flag value collision'; \
print('ALT_STANDSTILL=1024 OK, no collisions')"
```
Expected: `ALT_STANDSTILL=1024 OK, no collisions`

- [ ] **Step 3: Confirm the existing hyundai python suite still passes**

Run:
```bash
python -m pytest opendbc/car/hyundai/tests/test_hyundai.py -q
```
Expected: all pass (the flag<->safetyParam parity test at `test_hyundai.py` still passes because `ALT_STANDSTILL` is not yet attached to any platform).

- [ ] **Step 4: Commit**

```bash
git add opendbc/car/hyundai/values.py
git commit -m "hyundai: add ALT_STANDSTILL safety flag (personal fork)"
```

---

### Task 2: Refactor `HYUNDAI_COMMON_RX_CHECKS` to two params (behavior-preserving)

**Files:**
- Modify: `opendbc/safety/modes/hyundai.h` (macro definition ~lines 41-47; six call sites)
- Test: `opendbc/safety/tests/test_hyundai.py` (all existing hyundai safety tests must pass unchanged)

**Interfaces:**
- Produces: `HYUNDAI_COMMON_RX_CHECKS(whl_legacy, tcs13_legacy)` — `whl_legacy` gates 0x386 (WHL_SPD11) integrity, `tcs13_legacy` gates 0x394 (TCS13) integrity. Consumed by Task 3.

**Why this is a separate task:** the single-param macro applies the same `legacy` value to BOTH 0x386 and 0x394. Task 3 needs to relax only 0x386. Splitting the param first — as a pure, behavior-preserving refactor — isolates the risky arity change from the feature and lets the existing test suite prove it changed nothing.

- [ ] **Step 1: Change the macro to two params**

In `opendbc/safety/modes/hyundai.h`, replace:

```c
#define HYUNDAI_COMMON_RX_CHECKS(legacy)                                                                                                                                               \
  {.msg = {{0x260, 0, 8, 100U, .max_counter = 3U, .ignore_quality_flag = true},                                                                                           \
           {0x371, 0, 8, 100U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }}},                                                    \
  {.msg = {{0x386, 0, 8, 100U, .ignore_checksum = (legacy), .ignore_counter = (legacy), .max_counter = (legacy) ? 0U : 15U, .ignore_quality_flag = true}, { 0 }, { 0 }}}, \
  {.msg = {{0x394, 0, 8, 100U, .ignore_checksum = (legacy), .ignore_counter = (legacy), .max_counter = (legacy) ? 0U : 7U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  \
  {.msg = {{0x251, 0, 8, 50U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},                                              \
  {.msg = {{0x4F1, 0, 4, 50U, .ignore_checksum = true, .max_counter = 15U, .ignore_quality_flag = true}, { 0 }, { 0 }}},                                                  \
```

with:

```c
#define HYUNDAI_COMMON_RX_CHECKS(whl_legacy, tcs13_legacy)                                                                                                                             \
  {.msg = {{0x260, 0, 8, 100U, .max_counter = 3U, .ignore_quality_flag = true},                                                                                           \
           {0x371, 0, 8, 100U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }}},                                                    \
  {.msg = {{0x386, 0, 8, 100U, .ignore_checksum = (whl_legacy), .ignore_counter = (whl_legacy), .max_counter = (whl_legacy) ? 0U : 15U, .ignore_quality_flag = true}, { 0 }, { 0 }}}, \
  {.msg = {{0x394, 0, 8, 100U, .ignore_checksum = (tcs13_legacy), .ignore_counter = (tcs13_legacy), .max_counter = (tcs13_legacy) ? 0U : 7U, .ignore_quality_flag = true}, { 0 }, { 0 }}}, \
  {.msg = {{0x251, 0, 8, 50U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},                                              \
  {.msg = {{0x4F1, 0, 4, 50U, .ignore_checksum = true, .max_counter = 15U, .ignore_quality_flag = true}, { 0 }, { 0 }}},                                                  \
```

- [ ] **Step 2: Update all SIX call sites**

Every existing `HYUNDAI_COMMON_RX_CHECKS(...)` call in `opendbc/safety/modes/hyundai.h` must pass two args. Find them:
```bash
grep -n "HYUNDAI_COMMON_RX_CHECKS(" opendbc/safety/modes/hyundai.h
```
Expected: 7 lines — the macro definition plus 6 calls. Edit each **call** as follows (the five non-legacy calls become `(false, false)`; the one legacy call becomes `(true, true)`):

- `hyundai_long_rx_checks` (longitudinal): `HYUNDAI_COMMON_RX_CHECKS(false)` → `HYUNDAI_COMMON_RX_CHECKS(false, false)`
- `hyundai_fcev_long_rx_checks` (fcev long): `HYUNDAI_COMMON_RX_CHECKS(false)` → `HYUNDAI_COMMON_RX_CHECKS(false, false)`
- `hyundai_cam_scc_rx_checks` (camera scc): `HYUNDAI_COMMON_RX_CHECKS(false)` → `HYUNDAI_COMMON_RX_CHECKS(false, false)`
- `hyundai_rx_checks` (non-long): `HYUNDAI_COMMON_RX_CHECKS(false)` → `HYUNDAI_COMMON_RX_CHECKS(false, false)`  *(note: this line has 7-space indentation — edit it distinctly from the 3-space ones)*
- `hyundai_fcev_rx_checks` (fcev non-long): `HYUNDAI_COMMON_RX_CHECKS(false)` → `HYUNDAI_COMMON_RX_CHECKS(false, false)`
- `hyundai_legacy_rx_checks` (legacy mode): `HYUNDAI_COMMON_RX_CHECKS(true)` → `HYUNDAI_COMMON_RX_CHECKS(true, true)`

- [ ] **Step 3: Verify no single-arg calls remain**

Run:
```bash
grep -nE "HYUNDAI_COMMON_RX_CHECKS\((true|false)\)" opendbc/safety/modes/hyundai.h || echo "no single-arg calls remain"
```
Expected: `no single-arg calls remain`

- [ ] **Step 4: Build safety + run the full hyundai safety suite (proves refactor is behavior-preserving)**

Run:
```bash
scons -j8 opendbc/safety && python -m unittest opendbc.safety.tests.test_hyundai -v
```
Expected: compiles cleanly; the same test count as before this task, all `ok` (ending `OK (skipped=4)`). Any compile error means a missed/mis-edited call site — fix and rerun.

- [ ] **Step 5: Commit**

```bash
git add opendbc/safety/modes/hyundai.h
git commit -m "hyundai/safety: split HYUNDAI_COMMON_RX_CHECKS into (whl,tcs13) params (no behavior change)"
```

---

### Task 3: Implement `ALT_STANDSTILL` in panda safety (C) + unit tests

**Files:**
- Modify: `opendbc/safety/modes/hyundai_common.h` (param decode + new global bool)
- Modify: `opendbc/safety/modes/hyundai.h` (new relaxed long RX array; `vehicle_moving` from TCS13 in `hyundai_rx_hook`)
- Test: `opendbc/safety/tests/test_hyundai.py` (new class `TestHyundaiLongitudinalSafetyAltStandstill`)

**Interfaces:**
- Consumes: `HYUNDAI_COMMON_RX_CHECKS(whl_legacy, tcs13_legacy)` (Task 2); `HyundaiSafetyFlags.ALT_STANDSTILL == 1024` (Task 1).
- Produces: C global `hyundai_alt_standstill`; param `HYUNDAI_PARAM_ALT_STANDSTILL = 1024`; behavior — when the param bit is set, 0x386 RX integrity is skipped and `vehicle_moving = !TCS13.StandStill`.

- [ ] **Step 1 (TDD): Write the failing test class**

Append to `opendbc/safety/tests/test_hyundai.py`, immediately after the `TestHyundaiSafetyFCEVLong` class and before `if __name__`:

```python
class TestHyundaiLongitudinalSafetyAltStandstill(TestHyundaiLongitudinalSafety):
  """
    CAR.HYUNDAI_SONATA_LF_HYBRID (personal fork): non-legacy 'hyundai' safety with openpilot
    longitudinal. WHL_SPD11 (0x386) has no valid counter/checksum on this car, so
    HyundaiSafetyFlags.ALT_STANDSTILL exempts 0x386 from RX integrity and sources vehicle_moving
    from TCS13 (0x394) StandStill instead. TCS13 keeps full integrity checks; it carries both the
    brake (DriverOverride) and the standstill bit, so we model them together in one message.
  """
  cnt_tcs13 = 0

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai,
                                 HyundaiSafetyFlags.LONG | HyundaiSafetyFlags.HYBRID_GAS |
                                 HyundaiSafetyFlags.ALT_STANDSTILL)
    self.safety.init_tests()
    # TCS13 (0x394) carries both brake and standstill; track both so the two helpers emit a
    # single consistent message instead of clobbering each other.
    self._brake = False
    self._standstill = True

  # hybrid gas comes from E_EMS11 (0x371)
  def _user_gas_msg(self, gas):
    values = {"CR_Vcu_AccPedDep_Pos": gas}
    return self.packer.make_can_msg_safety("E_EMS11", 0, values, fix_checksum=checksum)

  def _tcs13_msg(self):
    values = {"DriverOverride": 2 if self._brake else 0,
              "StandStill": 1 if self._standstill else 0,
              "AliveCounterTCS": self.__class__.cnt_tcs13 % 8}
    self.__class__.cnt_tcs13 += 1
    return self.packer.make_can_msg_safety("TCS13", 0, values, fix_checksum=checksum)

  def _user_brake_msg(self, brake):
    self._brake = bool(brake)
    return self._tcs13_msg()

  # ALT_STANDSTILL: vehicle_moving is TCS13.StandStill, not WHL_SPD11
  def _vehicle_moving_msg(self, speed):
    self._standstill = speed <= self.STANDSTILL_THRESHOLD
    return self._tcs13_msg()

  def _whl_spd_bad_integrity_msg(self):
    # Mimic this car's WHL_SPD11 (0x386): frozen counter + invalid checksum (flip checksum bits).
    values = {"WHL_SPD_%s" % s: 20.0 for s in ["FL", "FR", "RL", "RR"]}
    values["WHL_SPD_AliveCounter_LSB"] = 0
    values["WHL_SPD_AliveCounter_MSB"] = 0
    def corrupt(msg):
      addr, dat, bus = checksum(msg)
      dat = bytearray(dat)
      dat[5] ^= 0xC0  # WHL_SPD11 checksum bits live in byte 5 high bits -> make invalid
      return addr, bytes(dat), bus
    return self.packer.make_can_msg_safety("WHL_SPD11", 0, values, fix_checksum=corrupt)

  def test_whl_spd_bad_integrity_allowed(self):
    # 0x386 lacks valid counter/checksum on this car; RX must NOT drop controls under ALT_STANDSTILL
    self.safety.set_controls_allowed(True)
    for _ in range(10):  # > MAX_WRONG_COUNTERS
      self.assertTrue(self._rx(self._whl_spd_bad_integrity_msg()))
      self.assertTrue(self.safety.get_controls_allowed())

  def test_tcs13_integrity_still_required(self):
    # 0x394 must stay strict: a bad checksum on TCS13 is rejected (not relaxed by ALT_STANDSTILL)
    def bad(msg):
      addr, dat, bus = checksum(msg)
      dat = bytearray(dat); dat[6] ^= 0x0F  # corrupt TCS13 checksum nibble
      return addr, bytes(dat), bus
    m = self.packer.make_can_msg_safety("TCS13", 0, {"AliveCounterTCS": 0}, fix_checksum=bad)
    self.assertFalse(self._rx(m))

  def test_vehicle_moving_from_tcs13(self):
    self._rx(self._vehicle_moving_msg(0.0))
    self.assertFalse(self.safety.get_vehicle_moving())      # StandStill=1 -> not moving
    self._rx(self._vehicle_moving_msg(5.0))
    self.assertTrue(self.safety.get_vehicle_moving())       # StandStill=0 -> moving
```

- [ ] **Step 2 (TDD): Run it and watch it fail**

Run:
```bash
python -m unittest opendbc.safety.tests.test_hyundai.TestHyundaiLongitudinalSafetyAltStandstill -v
```
Expected: FAIL — either `set_safety_hooks(...)` errors / does nothing meaningful (flag not decoded yet) or `test_vehicle_moving_from_tcs13` fails (vehicle_moving still tracks 0x386, not TCS13). This confirms the test exercises unimplemented behavior.

- [ ] **Step 3: Decode the new param bit (hyundai_common.h)**

In `opendbc/safety/modes/hyundai_common.h`, next to the other `bool hyundai_*` globals near the top (where `hyundai_alt_limits_2` is declared):

```c
extern bool hyundai_alt_limits_2;
bool hyundai_alt_limits_2 = false;
```

add:

```c
extern bool hyundai_alt_standstill;
bool hyundai_alt_standstill = false;
```

Then inside `hyundai_common_init`, after:

```c
  const uint16_t HYUNDAI_PARAM_ALT_LIMITS_2 = 512;
```
add:
```c
  const uint16_t HYUNDAI_PARAM_ALT_STANDSTILL = 1024;
```
and after:
```c
  hyundai_alt_limits_2 = GET_FLAG(param, HYUNDAI_PARAM_ALT_LIMITS_2);
```
add:
```c
  hyundai_alt_standstill = GET_FLAG(param, HYUNDAI_PARAM_ALT_STANDSTILL);
```

- [ ] **Step 4: Add the relaxed longitudinal RX-check array (hyundai.h)**

In `opendbc/safety/modes/hyundai.h`, inside `hyundai_init`, in the `if (hyundai_longitudinal) {` block, the arrays currently read:

```c
    static RxCheck hyundai_long_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(false, false)
    };

    static RxCheck hyundai_fcev_long_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(false, false)
      HYUNDAI_FCEV_GAS_ADDR_CHECK
    };

    if (hyundai_fcev_gas_signal) {
      SET_RX_CHECKS(hyundai_fcev_long_rx_checks, ret);
    } else {
      SET_RX_CHECKS(hyundai_long_rx_checks, ret);
    }
```

Change to (add the third array and prefer it when the flag is set):

```c
    static RxCheck hyundai_long_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(false, false)
    };

    static RxCheck hyundai_fcev_long_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(false, false)
      HYUNDAI_FCEV_GAS_ADDR_CHECK
    };

    // Personal fork (Sonata LF Hybrid): WHL_SPD11 (0x386) has no valid counter/checksum on this
    // car. Relax 0x386 integrity ONLY (0x394/TCS13 stays strict); vehicle_moving comes from TCS13.
    static RxCheck hyundai_long_alt_standstill_rx_checks[] = {
      HYUNDAI_COMMON_RX_CHECKS(true, false)
    };

    if (hyundai_alt_standstill) {
      SET_RX_CHECKS(hyundai_long_alt_standstill_rx_checks, ret);
    } else if (hyundai_fcev_gas_signal) {
      SET_RX_CHECKS(hyundai_fcev_long_rx_checks, ret);
    } else {
      SET_RX_CHECKS(hyundai_long_rx_checks, ret);
    }
```

- [ ] **Step 5: Source `vehicle_moving` from TCS13 when the flag is set (hyundai.h `hyundai_rx_hook`)**

Currently:

```c
    // sample wheel speed, averaging opposite corners
    if (msg->addr == 0x386U) {
      uint32_t front_left_speed = GET_BYTES(msg, 0, 2) & 0x3FFFU;
      uint32_t rear_right_speed = GET_BYTES(msg, 6, 2) & 0x3FFFU;
      vehicle_moving = (front_left_speed > HYUNDAI_STANDSTILL_THRSLD) || (rear_right_speed > HYUNDAI_STANDSTILL_THRSLD);
    }

    if (msg->addr == 0x394U) {
      brake_pressed = ((msg->data[5] >> 5U) & 0x3U) == 0x2U;
    }
```

Change to:

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

- [ ] **Step 6: Build + run the new test class to PASS**

Run:
```bash
scons -j8 opendbc/safety && python -m unittest opendbc.safety.tests.test_hyundai.TestHyundaiLongitudinalSafetyAltStandstill -v
```
Expected: all methods `ok` (inherited longitudinal tests + `test_whl_spd_bad_integrity_allowed`, `test_tcs13_integrity_still_required`, `test_vehicle_moving_from_tcs13`), ending `OK (skipped=4)`.

- [ ] **Step 7: Run the full safety suite + coverage gate (no regressions, 100% C coverage)**

Run:
```bash
python -m unittest opendbc.safety.tests.test_hyundai -v && ./opendbc/safety/tests/test.sh
```
Expected: all hyundai tests pass; `test.sh` (MISRA + `gcovr --fail-under-line=100`) passes. If coverage fails on the new branches, add a targeted assertion (e.g. also assert `vehicle_moving` under the non-flag path is still covered by the existing non-ALT class — it is).

- [ ] **Step 8: Commit**

```bash
git add opendbc/safety/modes/hyundai_common.h opendbc/safety/modes/hyundai.h opendbc/safety/tests/test_hyundai.py
git commit -m "hyundai/safety: ALT_STANDSTILL — relax 0x386 integrity, standstill from TCS13 (personal fork)"
```

---

### Task 4: Add the `HYUNDAI_SONATA_LF_HYBRID` platform + wire the safety param

**Files:**
- Modify: `opendbc/car/hyundai/values.py` (new `CAR` entry; add to `STEER_MAX = 255` bucket)
- Modify: `opendbc/car/hyundai/interface.py` (OR `ALT_STANDSTILL` into `safetyParam` — LOAD-BEARING)
- Modify: `opendbc/car/hyundai/fingerprints.py` (`FW_VERSIONS` entry)
- Modify: `opendbc/car/torque_data/substitute.toml`
- Modify: `opendbc/car/tests/routes.py`
- Modify: `opendbc/car/hyundai/tests/test_hyundai.py` (`no_eps_platforms`)
- Test: `opendbc/car/hyundai/tests/test_hyundai.py`

**Interfaces:**
- Consumes: `HyundaiSafetyFlags.ALT_STANDSTILL` (Task 1); `hyundai_alt_standstill` behavior (Task 3).
- Produces: `CAR.HYUNDAI_SONATA_LF_HYBRID`. carcontroller/hyundaican/carstate need **no change** — all longitudinal actuation is flag-driven off `HYBRID` + `openpilotLongitudinalControl` (verified).

- [ ] **Step 1: Add the platform config (values.py)**

In `opendbc/car/hyundai/values.py`, immediately after the `HYUNDAI_SONATA_LF` entry (before `HYUNDAI_STARIA_4TH_GEN`):

```python
  # Personal fork: LF Hybrid on standard 'hyundai' safety with openpilot longitudinal.
  # Flags include HYBRID and route-verified MANDO_RADAR: NO LEGACY (standard Hyundai safety),
  # NO UNSUPPORTED_LONGITUDINAL (keeps alphaLongitudinalAvailable True), NO TCU_GEARS (hybrid uses
  # ELECT_GEAR). 0x386 integrity is relaxed via HyundaiSafetyFlags.ALT_STANDSTILL set in interface.py.
  # A 116-minute highway route supports steerRatio 16.4. mass ~1595 kg (LF Hybrid curb), owner-refinable.
  HYUNDAI_SONATA_LF_HYBRID = HyundaiPlatformConfig(
    [HyundaiCarDocs("Hyundai Sonata Hybrid 2018-19", car_parts=CarParts.common([CarHarness.hyundai_e]),
                    support_type=SupportType.COMMUNITY, support_link="#community")],
    CarSpecs(mass=1595, wheelbase=2.804, steerRatio=16.4),
    flags=HyundaiFlags.HYBRID | HyundaiFlags.MANDO_RADAR,
  )
```

> **MANDO_RADAR follow-up:** the backed-up Alpha Long route contains all bus-1 `0x500-0x51f`
> addresses after bus-0 SCC normal-communication disable: 1,189,330 frames at about 20 Hz.
> Current-code RadarInterface replay ends valid on every segment. Full RadarD lead selection and
> false-lead behavior remain an on-car validation gate.

- [ ] **Step 2: Add to the `STEER_MAX = 255` bucket (values.py)**

In `CarControllerParams.__init__`, the `elif CP.carFingerprint in (...)` tuple that sets `self.STEER_MAX = 255` currently contains `CAR.HYUNDAI_SONATA_LF`. Add the hybrid right after it:

```python
    elif CP.carFingerprint in (CAR.GENESIS_G80, CAR.HYUNDAI_ELANTRA, CAR.HYUNDAI_ELANTRA_GT_I30, CAR.HYUNDAI_IONIQ,
                               CAR.HYUNDAI_IONIQ_EV_LTD, CAR.HYUNDAI_SANTA_FE_PHEV_2022, CAR.HYUNDAI_SONATA_LF, CAR.HYUNDAI_SONATA_LF_HYBRID,
                               CAR.KIA_FORTE, CAR.KIA_NIRO_PHEV, CAR.KIA_OPTIMA_H, CAR.KIA_OPTIMA_H_G4_FL, CAR.KIA_SORENTO):
      self.STEER_MAX = 255
```

- [ ] **Step 3: Wire the safety param (interface.py) — LOAD-BEARING**

In `opendbc/car/hyundai/interface.py`, in the car-specific overrides section (after the `KIA_OPTIMA_G4_FL` `steerActuatorDelay` override, before the `ALT_LIMITS_2` dashcam block), add:

```python
    if candidate == CAR.KIA_OPTIMA_G4_FL:
      ret.steerActuatorDelay = 0.2

    # Personal fork: LF Hybrid runs standard 'hyundai' safety but WHL_SPD11 (0x386) lacks a valid
    # counter/checksum. Tell the panda RX check to skip 0x386 integrity and use TCS13 (0x394)
    # StandStill for vehicle_moving. Without this line the panda faults 0x386 and never engages.
    if candidate == CAR.HYUNDAI_SONATA_LF_HYBRID:
      ret.safetyConfigs[-1].safetyParam |= HyundaiSafetyFlags.ALT_STANDSTILL.value
```

> No edits needed at `interface.py:87` (alphaLongitudinalAvailable) or `:98-102` (safety-mode select): because the platform carries neither `LEGACY` nor `UNSUPPORTED_LONGITUDINAL`, line 87 yields `alphaLongitudinalAvailable = True` and line 102 selects standard `hyundai` safety automatically. `openpilotLongitudinalControl` then becomes `alpha_long and True`, and `HyundaiSafetyFlags.LONG`/`HYBRID_GAS` are OR'd in at lines 138/140.

- [ ] **Step 4: Add the FW fingerprint (fingerprints.py)**

In `opendbc/car/hyundai/fingerprints.py`, add to the `FW_VERSIONS` dict:

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

- [ ] **Step 5: Torque substitution (substitute.toml)**

In `opendbc/car/torque_data/substitute.toml`, add (torque tune shared with the LF platform):

```toml
"HYUNDAI_SONATA_LF_HYBRID" = "HYUNDAI_SONATA_LF"
```

- [ ] **Step 6: Test route (routes.py)**

In `opendbc/car/tests/routes.py`, add near the other Hyundai routes:

```python
  CarTestRoute("9f9b411a57b8ce21/00000001--d6d081f0e7", HYUNDAI.HYUNDAI_SONATA_LF_HYBRID),
```

- [ ] **Step 7: EPS exclusion (test_hyundai.py)**

In `opendbc/car/hyundai/tests/test_hyundai.py`, add `CAR.HYUNDAI_SONATA_LF_HYBRID` to the `no_eps_platforms` set (this platform has no EPS query, like the ICE LF):

```python
    no_eps_platforms = CANFD_CAR | {CAR.KIA_SORENTO, CAR.KIA_OPTIMA_G4, CAR.KIA_OPTIMA_G4_FL, CAR.KIA_OPTIMA_H, CAR.KIA_K7_2017,
                                    CAR.KIA_OPTIMA_H_G4_FL, CAR.HYUNDAI_SONATA_LF, CAR.HYUNDAI_TUCSON, CAR.GENESIS_G90, CAR.GENESIS_G80, CAR.HYUNDAI_ELANTRA,
                                    CAR.HYUNDAI_SONATA_LF_HYBRID}
```

- [ ] **Step 8: Verify the platform resolves to a longitudinal-capable, correctly-flagged CarParams**

Run:
```bash
python -c "
from opendbc.car.hyundai.values import CAR, HyundaiSafetyFlags
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car import structs, gen_empty_fingerprint
CP = CarInterface.get_params(CAR.HYUNDAI_SONATA_LF_HYBRID, gen_empty_fingerprint(), [], alpha_long=True, is_release=False, docs=False)
assert CP.openpilotLongitudinalControl, 'long not enabled'
assert CP.safetyConfigs[-1].safetyModel == structs.CarParams.SafetyModel.hyundai, CP.safetyConfigs[-1].safetyModel
p = CP.safetyConfigs[-1].safetyParam
for f in (HyundaiSafetyFlags.LONG, HyundaiSafetyFlags.HYBRID_GAS, HyundaiSafetyFlags.ALT_STANDSTILL):
    assert p & f.value, f'missing {f.name}'
print('OK: hyundai safety, long ON, param has LONG|HYBRID_GAS|ALT_STANDSTILL')
"
```
Expected: `OK: hyundai safety, long ON, param has LONG|HYBRID_GAS|ALT_STANDSTILL`
(The exact `get_params` signature may vary by opendbc version; if it differs, match the signature used in `opendbc/car/tests/test_models.py`.)

- [ ] **Step 9: Run the hyundai car test suite**

Run:
```bash
python -m pytest opendbc/car/hyundai/tests/test_hyundai.py -q
```
Expected: all pass — including fuzzy-fingerprint, `test_platform_code_ecus_available` (car is in `no_eps_platforms`), and the hybrid-not-in-CAN_GEARS check (car has no `TCU_GEARS`).

- [ ] **Step 10: Confirm the actuation files are untouched**

Run:
```bash
git diff --stat opendbc/car/hyundai/carcontroller.py opendbc/car/hyundai/hyundaican.py opendbc/car/hyundai/carstate.py
```
Expected: no output (zero changes) — proof the actuation/state path needed no edits.

- [ ] **Step 11: Commit**

```bash
git add opendbc/car/hyundai/values.py opendbc/car/hyundai/interface.py opendbc/car/hyundai/fingerprints.py \
        opendbc/car/torque_data/substitute.toml opendbc/car/tests/routes.py opendbc/car/hyundai/tests/test_hyundai.py
git commit -m "hyundai: add Sonata LF Hybrid on standard safety with openpilot longitudinal (personal fork)"
```

---

### Task 5: Offline replay validation against the owner's route

**Files:**
- Create: `opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py`

**Interfaces:**
- Consumes: `CAR.HYUNDAI_SONATA_LF_HYBRID` (Task 4), `HyundaiSafetyFlags.ALT_STANDSTILL` (Task 1).
- Produces: an executable script that proves the RX/parse/plumbing path on real recorded CAN.

**Why:** validates end-to-end that the interface builds a longitudinal-capable CarParams and parses this car's real CAN (speeds/cruise/brake/gas/standstill) without error. It CANNOT prove actuation (route was recorded on stock ACC) — documented in the script.

- [ ] **Step 1: Write the replay script**

Create `opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py`:

```python
#!/usr/bin/env python3
"""Offline replay validation for openpilot-longitudinal PLUMBING on CAR.HYUNDAI_SONATA_LF_HYBRID.

Reads the owner's THREE LOCAL rlog.zst segments directly (not the comma_car_segments network
dataset). Proves: (1) LogReader decodes the logs, (2) get_params yields openpilotLongitudinalControl
with the hyundai safety model + LONG|HYBRID_GAS|ALT_STANDSTILL param bits, (3) every CAN frame flows
through CarInterface.update() without raising and CarState signals stay in range, (4) TCS13.StandStill
polarity matches speed (regression guard for the load-bearing assumption).

Does NOT prove actuation: the route was recorded on stock ACC, so only RX/plumbing is exercised.

Run:
  uv run --with zstandard python opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py
"""
import sys
import math

from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.can_definitions import CanData
from opendbc.car.car_helpers import interfaces
from opendbc.car.hyundai.values import CAR, HyundaiSafetyFlags
from opendbc.car.logreader import LogReader
from opendbc.can.parser import CANParser

PLATFORM = CAR.HYUNDAI_SONATA_LF_HYBRID
SEGMENTS = sys.argv[1:] or [
  "/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--0--rlog.zst",
  "/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--2--rlog.zst",
  "/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--3--rlog.zst",
]


def load_can(paths):
  events = []
  for p in paths:
    seg = [m for m in LogReader(p, only_union_types=True, sort_by_time=True) if m.which() == "can"]
    print(f"  {p}: {len(seg)} can events")
    events.extend(seg)
  events.sort(key=lambda m: m.logMonoTime)
  return events


def check_params():
  CI = interfaces[PLATFORM]
  CP = CI.get_params(PLATFORM, gen_empty_fingerprint(), [], alpha_long=True, is_release=False, docs=False)
  assert CP.openpilotLongitudinalControl, "openpilotLongitudinalControl is False"
  assert CP.safetyConfigs[-1].safetyModel == structs.CarParams.SafetyModel.hyundai, "not on hyundai safety"
  p = CP.safetyConfigs[-1].safetyParam
  for f in (HyundaiSafetyFlags.LONG, HyundaiSafetyFlags.HYBRID_GAS, HyundaiSafetyFlags.ALT_STANDSTILL):
    assert p & f.value, f"safetyParam missing {f.name}"
  print("  CarParams OK: hyundai safety, long ON, param LONG|HYBRID_GAS|ALT_STANDSTILL")
  return CP, CI


def replay_state(CP, CI, can_msgs):
  ci = CI(CP)
  CC = structs.CarControl().as_reader()
  vmax = 0.0
  n = 0
  for m in can_msgs:
    frames = [CanData(c.address, c.dat, c.src) for c in m.can]
    cs = ci.update([(m.logMonoTime, frames)])
    ci.apply(CC, m.logMonoTime)
    vmax = max(vmax, cs.vEgo)
    assert -1.0 <= cs.vEgo <= 80.0, f"vEgo out of range: {cs.vEgo}"
    n += 1
  print(f"  replayed {n} frames without error; max vEgo={vmax * 3.6:.1f} km/h")


def check_standstill_polarity(can_msgs):
  cp = CANParser("hyundai_can_generated", [("TCS13", 0), ("WHL_SPD11", 0)], 0)
  stopped_bit1 = stopped_n = moving_bit0 = moving_n = 0
  for m in can_msgs:
    cp.update((m.logMonoTime, [(c.address, bytes(c.dat), c.src) for c in m.can]))
    ss = int(round(cp.vl["TCS13"]["StandStill"]))
    w = cp.vl["WHL_SPD11"]
    v = (w["WHL_SPD_FL"] + w["WHL_SPD_FR"] + w["WHL_SPD_RL"] + w["WHL_SPD_RR"]) / 4.0
    if v < 0.3:
      stopped_n += 1; stopped_bit1 += (ss == 1)
    elif v > 5.0:
      moving_n += 1; moving_bit0 += (ss == 0)
  r_stop = stopped_bit1 / max(stopped_n, 1)
  r_move = moving_bit0 / max(moving_n, 1)
  print(f"  StandStill polarity: stopped->1 {100*r_stop:.1f}%, moving->0 {100*r_move:.1f}%")
  assert r_stop > 0.9 and r_move > 0.9, "StandStill polarity FAILED — vehicle_moving = !bit47 is wrong"


def main():
  print("Loading segments:")
  can_msgs = load_can(SEGMENTS)
  print("Checking CarParams:")
  CP, CI = check_params()
  print("Replaying CarState:")
  replay_state(CP, CI, can_msgs)
  print("Checking StandStill polarity (regression guard):")
  check_standstill_polarity(can_msgs)
  print("\nALL OFFLINE CHECKS PASSED (plumbing only; actuation is on-car).")


if __name__ == "__main__":
  main()
```

- [ ] **Step 2: Run it**

Run:
```bash
uv run --with zstandard python opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py
```
Expected (approximate):
```
  ...--0--rlog.zst: 6120 can events
  ...
  CarParams OK: hyundai safety, long ON, param LONG|HYBRID_GAS|ALT_STANDSTILL
  replayed 18121 frames without error; max vEgo=36.6 km/h
  StandStill polarity: stopped->1 98.2%, moving->0 100.0%
ALL OFFLINE CHECKS PASSED (plumbing only; actuation is on-car).
```

- [ ] **Step 3: Commit**

```bash
git add opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py
git commit -m "hyundai: offline replay validation for Sonata LF Hybrid longitudinal (personal fork)"
```

---

### Task 6: On-car bring-up documentation

**Files:**
- Create: `docs/sonata-lf-hev-long-oncar.md`

**Why:** the offline tasks cannot verify the two runtime-only facts (radar 0x7D0 disable acceptance; real actuation/ride). This documents the fork/flash workflow, the on-car checklist, the accepted tradeoffs, and the abort criteria.

- [ ] **Step 1: Write the doc**

Create `docs/sonata-lf-hev-long-oncar.md`:

```markdown
# Sonata LF Hybrid — openpilot longitudinal on-car bring-up (personal fork)

## What this fork changes
- Moves CAR.HYUNDAI_SONATA_LF_HYBRID onto standard `hyundai` panda safety (not `hyundaiLegacy`).
- Adds `HyundaiSafetyFlags.ALT_STANDSTILL` (1024): relaxes only WHL_SPD11 (0x386) RX integrity
  (that message has no valid counter/checksum on this car) and derives `vehicle_moving` from the
  integrity-valid TCS13 (0x394) `StandStill` bit.
- Enables openpilot longitudinal availability; all actuation is the stock hyundai flag-driven path.

## Build / flash (openpilot side — outside opendbc)
1. openpilot vendors opendbc as the `opendbc_repo` submodule. Point it at this fork's
   `sonata-lf-hev-long` branch (add fork remote, fetch, checkout inside `opendbc_repo`).
2. Run openpilot's build (`scons`). The panda firmware is compiled FROM the vendored opendbc/safety
   and auto-flashed by `pandad` on the next boot when its signature changes. No manual DFU needed.
3. MUST be a NON-RELEASE branch: `hyundai_longitudinal` is behind `#ifdef ALLOW_DEBUG`, and the
   "openpilot Longitudinal Control (Alpha)" toggle is hidden on release branches.
4. Hardware: comma 3/3X + the correct in-line Hyundai harness (must sit between the radar and the
   rest of the bus so panda can both inject SCC12 and issue the 0x7D0 disable).

## Enable at runtime
- Toggle **openpilot Longitudinal Control (Alpha)** (param `AlphaLongitudinalEnabled`). It is only
  visible because `alphaLongitudinalAvailable` is now True for this car.

## On-car checklist (in order, abort if any step fails)
1. Engage on a safe, empty road at low speed. Confirm openpilot ACC engages (not stock cruise).
2. **Radar disable (the key unknown):** confirm the stock radar stops transmitting SCC — i.e. no
   "SCC conditions not met" fight, no dual-SCC on the bus. If the radar refuses the 0x7D0 disable,
   openpilot ACC and factory SCC will conflict — ABORT and revert; this car is not viable without
   a working radar disable.
3. Verify standstill: at a full stop, openpilot holds; on lead pull-away it resumes cleanly
   (this exercises TCS13.StandStill sourcing).
4. Verify driver override: tap the brake -> immediate disengage; press the gas -> override.
5. Evaluate ride quality (jerk, stopping distance, creep). The tune is the generic hyundai
   longitudinal tune; if stops are harsh, that is tuning, not a safety issue.

## Accepted tradeoffs / known limits
- **Factory AEB/FCW is lost** while openpilot longitudinal is on (radar is disabled). This is
  inherent to radar-SCC openpilot longitudinal, not specific to this fork.
- Longitudinal tune is not validated for this exact car; ride quality may differ from stock SCC.
- steerRatio is `16.4`, supported by a 116-minute highway route with qualified median `16.402`.

## Do not
- Do not run on a release branch. Do not open an upstream PR (this relaxes a safety check for one
  car). Do not treat offline MANDO parsing as final lead-quality validation; verify false leads and cut-ins on-car.
```

- [ ] **Step 2: Commit**

```bash
git add docs/sonata-lf-hev-long-oncar.md
git commit -m "docs: Sonata LF Hybrid longitudinal on-car bring-up checklist (personal fork)"
```

---

## Self-Review

**Spec coverage:**
- Move off legacy → standard hyundai safety: Task 4 Step 1 (no LEGACY flag) + Step 3 (auto-selects hyundai).
- New per-car flag, per-car only (not global): Task 1 (python), Task 3 Steps 3-5 (C, gated on `hyundai_alt_standstill`).
- 0x386 relaxed, 0x394 stays strict: Task 2 (2-param macro) + Task 3 Step 4 (`(true, false)`), asserted by `test_tcs13_integrity_still_required`.
- vehicle_moving from TCS13: Task 3 Step 5, asserted by `test_vehicle_moving_from_tcs13` + replay polarity guard (Task 5).
- Enable longitudinal availability: Task 4 Step 3 + Step 8 assertion.
- Interface safetyParam OR-in (load-bearing): Task 4 Step 3.
- Actuation unchanged: Task 4 Step 10 (zero-diff proof).
- Offline validation: Task 5.
- Runtime unknowns + tradeoffs + fork/flash: Task 6.

**Placeholder scan:** none — every code step has full before/after; every run step has exact command + expected output.

**Type/name consistency:** flag is `ALT_STANDSTILL` / value `1024` on both python (`HyundaiSafetyFlags.ALT_STANDSTILL`, Task 1) and C (`HYUNDAI_PARAM_ALT_STANDSTILL`, global `hyundai_alt_standstill`, Task 3); referenced identically in Task 4 (OR-in) and the test class (Task 3) and replay (Task 5). Macro `HYUNDAI_COMMON_RX_CHECKS(whl_legacy, tcs13_legacy)` defined in Task 2 and consumed in Task 3 with the same arg order.

**Open items intentionally left to the owner (not gaps):** exact hybrid `mass`; final `steerRatio` from a highway `liveParameters` capture. Neither blocks a working config.
