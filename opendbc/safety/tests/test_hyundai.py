#!/usr/bin/env python3
from opendbc.testing import parameterized_class
import random
import unittest

from opendbc.car.hyundai.values import HyundaiSafetyFlags
from opendbc.car.structs import CarParams
from opendbc.safety.tests.libsafety import libsafety_py
import opendbc.safety.tests.common as common
from opendbc.safety.tests.common import CANPackerSafety
from opendbc.safety.tests.hyundai_common import HyundaiButtonBase, HyundaiLongitudinalBase

from opendbc.sunnypilot.car.hyundai.values import HyundaiSafetyFlagsSP

# LDA button availability
LDA_BUTTON = [
  {"SAFETY_PARAM_SP": HyundaiSafetyFlagsSP.DEFAULT},
  {"SAFETY_PARAM_SP": HyundaiSafetyFlagsSP.HAS_LDA_BUTTON},
]

# All combinations of non-SCC HEV/PHEV/EV cars
_ALL_NON_SCC_HEV_EV_COMBOS = [
  # Hybrid
  {"PCM_STATUS_MSG": ("E_CRUISE_CONTROL", "CRUISE_LAMP_S"),
   "ACC_STATE_MSG": ("E_CRUISE_CONTROL", "CRUISE_LAMP_M"),
   "GAS_MSG": ("E_EMS11", "CR_Vcu_AccPedDep_Pos"),
   "SAFETY_PARAM": HyundaiSafetyFlags.HYBRID_GAS},
  # EV
  {"PCM_STATUS_MSG": ("LABEL11", "CC_ACT"),
   "ACC_STATE_MSG": ("LABEL11", "CC_React"),
   "GAS_MSG": ("E_EMS11", "Accel_Pedal_Pos"),
   "SAFETY_PARAM": HyundaiSafetyFlags.EV_GAS},
]
ALL_NON_SCC_HEV_EV_COMBOS = [{**p, **lda} for lda in LDA_BUTTON for p in _ALL_NON_SCC_HEV_EV_COMBOS]


# 4 bit checkusm used in some hyundai messages
# lives outside the can packer because we never send this msg
def checksum(msg):
  addr, dat, bus = msg

  chksum = 0
  if addr == 0x386:
    for i, b in enumerate(dat):
      for j in range(8):
        # exclude checksum and counter bits
        if (i != 1 or j < 6) and (i != 3 or j < 6) and (i != 5 or j < 6) and (i != 7 or j < 6):
          bit = (b >> j) & 1
        else:
          bit = 0
        chksum += bit
    chksum = (chksum ^ 9) & 0xF
    ret = bytearray(dat)
    ret[5] |= (chksum & 0x3) << 6
    ret[7] |= (chksum & 0xc) << 4
  else:
    for i, b in enumerate(dat):
      if addr in [0x260, 0x421] and i == 7:
        b &= 0x0F if addr == 0x421 else 0xF0
      elif addr == 0x394 and i == 6:
        b &= 0xF0
      elif addr == 0x394 and i == 7:
        continue
      chksum += sum(divmod(b, 16))
    chksum = (16 - chksum) % 16
    ret = bytearray(dat)
    ret[6 if addr == 0x394 else 7] |= chksum << (4 if addr == 0x421 else 0)

  return addr, ret, bus


@parameterized_class(LDA_BUTTON)
class TestHyundaiSafety(HyundaiButtonBase, common.CarSafetyTest, common.DriverTorqueSteeringSafetyTest, common.SteerRequestCutSafetyTest):
  TX_MSGS = [[0x340, 0], [0x4F1, 0], [0x485, 0]]
  STANDSTILL_THRESHOLD = 12  # 0.375 kph
  RELAY_MALFUNCTION_ADDRS = {0: (0x340, 0x485)}  # LKAS11
  FWD_BLACKLISTED_ADDRS = {2: [0x340, 0x485]}

  MAX_RATE_UP = 3
  MAX_RATE_DOWN = 7
  MAX_TORQUE_LOOKUP = [0], [384]
  MAX_RT_DELTA = 112
  DRIVER_TORQUE_ALLOWANCE = 50
  DRIVER_TORQUE_FACTOR = 2

  # Safety around steering req bit
  MIN_VALID_STEERING_FRAMES = 89
  MAX_INVALID_STEERING_FRAMES = 2

  cnt_gas = 0
  cnt_speed = 0
  cnt_brake = 0
  cnt_cruise = 0
  cnt_button = 0

  SAFETY_PARAM_SP: int = 0

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiSafety":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, 0)
    self.safety.init_tests()

  def _button_msg(self, buttons, main_button=0, bus=0):
    values = {"CF_Clu_CruiseSwState": buttons, "CF_Clu_CruiseSwMain": main_button, "CF_Clu_AliveCnt1": self.cnt_button}
    self.__class__.cnt_button += 1
    return self.packer.make_can_msg_safety("CLU11", bus, values)

  def _user_gas_msg(self, gas):
    values = {"CF_Ems_AclAct": gas, "AliveCounter": self.cnt_gas % 4}
    self.__class__.cnt_gas += 1
    return self.packer.make_can_msg_safety("EMS16", 0, values, fix_checksum=checksum)

  def _user_brake_msg(self, brake):
    values = {"DriverOverride": 2 if brake else random.choice((0, 1, 3)),
              "AliveCounterTCS": self.cnt_brake % 8}
    self.__class__.cnt_brake += 1
    return self.packer.make_can_msg_safety("TCS13", 0, values, fix_checksum=checksum)

  def _speed_msg(self, speed):
    # safety doesn't scale, so undo the scaling
    values = {"WHL_SPD_%s" % s: speed * 0.03125 for s in ["FL", "FR", "RL", "RR"]}
    values["WHL_SPD_AliveCounter_LSB"] = (self.cnt_speed % 16) & 0x3
    values["WHL_SPD_AliveCounter_MSB"] = (self.cnt_speed % 16) >> 2
    self.__class__.cnt_speed += 1
    return self.packer.make_can_msg_safety("WHL_SPD11", 0, values, fix_checksum=checksum)

  def _pcm_status_msg(self, enable):
    values = {"ACCMode": enable, "CR_VSM_Alive": self.cnt_cruise % 16}
    self.__class__.cnt_cruise += 1
    return self.packer.make_can_msg_safety("SCC12", self.SCC_BUS, values, fix_checksum=checksum)

  def _torque_driver_msg(self, torque):
    values = {"CR_Mdps_StrColTq": torque}
    return self.packer.make_can_msg_safety("MDPS12", 0, values)

  def _torque_cmd_msg(self, torque, steer_req=1):
    values = {"CR_Lkas_StrToqReq": torque, "CF_Lkas_ActToi": steer_req}
    return self.packer.make_can_msg_safety("LKAS11", 0, values)

  def _acc_state_msg(self, enable):
    values = {"MainMode_ACC": enable}
    return self.packer.make_can_msg_safety("SCC11", self.SCC_BUS, values)

  def _lkas_button_msg(self, enabled):
    if self.SAFETY_PARAM_SP & HyundaiSafetyFlagsSP.HAS_LDA_BUTTON:
      values = {"LDA_BTN": enabled}
      return self.packer.make_can_msg_safety("BCM_PO_11", 0, values)
    else:
      raise NotImplementedError

  def _main_cruise_button_msg(self, enabled):
    return self._button_msg(0, enabled)

  def test_pcm_main_cruise_state_availability(self):
    """Test that ACC main state is correctly set when receiving SCC11 (0x420), toggling HYUNDAI_LONG flag.

    Only applicable to SCC-based cars. Non-SCC cars use different messages for ACC state
    and their rx_checks don't include SCC11 after mode reconfiguration.
    """
    if any('NonSCC' in cls.__name__ for cls in type(self).__mro__):
      raise unittest.SkipTest("Non-SCC cars use different ACC state messages, not SCC11")

    prior_safety_mode = self.safety.get_current_safety_mode()
    prior_safety_param = self.safety.get_current_safety_param()
    safety_param_sp = self.SAFETY_PARAM_SP

    for hyundai_longitudinal in (True, False):
      with self.subTest("hyundai_longitudinal", hyundai_longitudinal=hyundai_longitudinal):
        self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
        self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, 0 if hyundai_longitudinal else HyundaiSafetyFlags.LONG)
        for should_turn_acc_main_on in (True, False):
          with self.subTest("acc_main_on", should_turn_acc_main_on=should_turn_acc_main_on):
            self.safety.set_acc_main_on(False)
            self._rx(self._acc_state_msg(should_turn_acc_main_on))
            expected_acc_main = should_turn_acc_main_on and hyundai_longitudinal
            self.assertEqual(expected_acc_main, self.safety.get_acc_main_on())
    self.safety.set_current_safety_param_sp(safety_param_sp)
    self.safety.set_safety_hooks(prior_safety_mode, prior_safety_param)
    self.safety.init_tests()

  def test_enable_control_allowed_with_mads_button(self):
    """Toggle MADS with MADS button, testing HAS_LDA_BUTTON param gating."""
    default_safety_mode = self.safety.get_current_safety_mode()
    default_safety_param = self.safety.get_current_safety_param()
    default_safety_param_sp = self.SAFETY_PARAM_SP

    try:
      self._lkas_button_msg(False)
    except NotImplementedError as err:
      raise unittest.SkipTest("Skipping test because LDA button is not supported") from err

    # CameraSCC rx_checks always include BCM_PO_11 regardless of HAS_LDA_BUTTON param,
    # so we can only test the has_lda_button=True case for CameraSCC.
    camera_scc = bool(default_safety_param & HyundaiSafetyFlags.CAMERA_SCC)
    lda_button_variants = [True] if camera_scc else [True, False]

    try:
      for enable_mads in (True, False):
        with self.subTest("enable_mads", mads_enabled=enable_mads):
          for has_lda_button_param in lda_button_variants:
            with self.subTest("has_lda_button", has_lda_button_param=has_lda_button_param):
              has_lda_button = HyundaiSafetyFlagsSP.HAS_LDA_BUTTON if has_lda_button_param else 0
              sp = (default_safety_param_sp & ~HyundaiSafetyFlagsSP.HAS_LDA_BUTTON) | has_lda_button
              self.safety.set_current_safety_param_sp(sp)
              self.safety.set_safety_hooks(default_safety_mode, default_safety_param)
              self.safety.init_tests()

              self.safety.set_controls_allowed(False)
              self.safety.set_acc_main_on(False)
              self.safety.set_controls_allowed_lateral(False)
              self.safety.set_mads_params(enable_mads, False, False)
              self.assertEqual(enable_mads, self.safety.get_enable_mads())

              self._rx(self._lkas_button_msg(True))
              self._rx(self._lkas_button_msg(False))
              self.assertEqual(enable_mads and has_lda_button_param, self.safety.get_controls_allowed_lateral())
    finally:
      self.safety.set_current_safety_param_sp(default_safety_param_sp)


@parameterized_class(LDA_BUTTON)
class TestHyundaiSafetyAltLimits(TestHyundaiSafety):
  MAX_RATE_UP = 2
  MAX_RATE_DOWN = 3
  MAX_TORQUE_LOOKUP = [0], [270]

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiSafetyAltLimits":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.ALT_LIMITS)
    self.safety.init_tests()


@parameterized_class(LDA_BUTTON)
class TestHyundaiSafetyAltLimits2(TestHyundaiSafety):
  MAX_RATE_UP = 2
  MAX_RATE_DOWN = 3
  MAX_TORQUE_LOOKUP = [0], [170]

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiSafetyAltLimits2":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.ALT_LIMITS_2)
    self.safety.init_tests()


@parameterized_class(LDA_BUTTON)
class TestHyundaiSafetyCameraSCC(TestHyundaiSafety):
  BUTTONS_TX_BUS = 2  # tx on 2, rx on 0
  SCC_BUS = 2  # rx on 2

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiSafetyCameraSCC":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.CAMERA_SCC)
    self.safety.init_tests()

  def test_pcm_main_cruise_state_availability(self):
    """
    Test that ACC main state is correctly set when receiving 0x420 message.
    For camera SCC, ACC main should always be on when receiving 0x420 message
    """

    for should_turn_acc_main_on in (True, False):
      with self.subTest("acc_main_on", should_turn_acc_main_on=should_turn_acc_main_on):
        self._rx(self._acc_state_msg(should_turn_acc_main_on))
        self.assertEqual(should_turn_acc_main_on, self.safety.get_acc_main_on())


@parameterized_class(LDA_BUTTON)
class TestHyundaiSafetyFCEV(TestHyundaiSafety):
  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiSafetyFCEV":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.FCEV_GAS)
    self.safety.init_tests()

  def _user_gas_msg(self, gas):
    values = {"ACCELERATOR_PEDAL": gas}
    return self.packer.make_can_msg_safety("FCEV_ACCELERATOR", 0, values)


class TestHyundaiLegacySafety(TestHyundaiSafety):
  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundaiLegacy, 0)
    self.safety.init_tests()


class TestHyundaiLegacySafetyEV(TestHyundaiSafety):
  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundaiLegacy, HyundaiSafetyFlags.EV_GAS)
    self.safety.init_tests()

  def _user_gas_msg(self, gas):
    values = {"Accel_Pedal_Pos": gas}
    return self.packer.make_can_msg_safety("E_EMS11", 0, values, fix_checksum=checksum)


class TestHyundaiLegacySafetyHEV(TestHyundaiSafety):
  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundaiLegacy, HyundaiSafetyFlags.HYBRID_GAS)
    self.safety.init_tests()

  def _user_gas_msg(self, gas):
    values = {"CR_Vcu_AccPedDep_Pos": gas}
    return self.packer.make_can_msg_safety("E_EMS11", 0, values, fix_checksum=checksum)


@parameterized_class(LDA_BUTTON)
class TestHyundaiLongitudinalSafety(HyundaiLongitudinalBase, TestHyundaiSafety):
  TX_MSGS = [[0x340, 0], [0x4F1, 0], [0x485, 0], [0x420, 0], [0x421, 0], [0x50A, 0], [0x389, 0], [0x4A2, 0], [0x38D, 0], [0x483, 0], [0x7D0, 0]]

  FWD_BLACKLISTED_ADDRS = {2: [0x340, 0x485, 0x421, 0x420, 0x50A, 0x389]}

  RELAY_MALFUNCTION_ADDRS = {0: (0x340, 0x485, 0x421, 0x420, 0x50A, 0x389)}  # LKAS11, LFAHDA_MFC, SCC12, SCC11, SCC13, SCC14

  DISABLED_ECU_UDS_MSG = (0x7D0, 0)
  DISABLED_ECU_ACTUATION_MSG = (0x421, 0)

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiLongitudinalSafety":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.LONG)
    self.safety.init_tests()

  def _accel_msg(self, accel, aeb_req=False, aeb_decel=0):
    values = {
      "aReqRaw": accel,
      "aReqValue": accel,
      "AEB_CmdAct": int(aeb_req),
      "CR_VSM_DecCmd": aeb_decel,
    }
    return self.packer.make_can_msg_safety("SCC12", self.SCC_BUS, values)

  def _fca11_msg(self, idx=0, vsm_aeb_req=False, fca_aeb_req=False, aeb_decel=0):
    values = {
      "CR_FCA_Alive": idx % 0xF,
      "FCA_Status": 2,
      "CR_VSM_DecCmd": aeb_decel,
      "CF_VSM_DecCmdAct": int(vsm_aeb_req),
      "FCA_CmdAct": int(fca_aeb_req),
    }
    return self.packer.make_can_msg_safety("FCA11", 0, values)

  def _tx_acc_state_msg(self, enable):
    values = {"MainMode_ACC": enable}
    return self.packer.make_can_msg_safety("SCC11", 0, values)

  def test_no_aeb_fca11(self):
    self.assertTrue(self._tx(self._fca11_msg()))
    self.assertFalse(self._tx(self._fca11_msg(vsm_aeb_req=True)))
    self.assertFalse(self._tx(self._fca11_msg(fca_aeb_req=True)))
    self.assertFalse(self._tx(self._fca11_msg(aeb_decel=1.0)))

  def test_no_aeb_scc12(self):
    self.assertTrue(self._tx(self._accel_msg(0)))
    self.assertFalse(self._tx(self._accel_msg(0, aeb_req=True)))
    self.assertFalse(self._tx(self._accel_msg(0, aeb_decel=1.0)))


class TestHyundaiLongitudinalSafetyCameraSCC(HyundaiLongitudinalBase, TestHyundaiSafety):
  TX_MSGS = [[0x340, 0], [0x4F1, 2], [0x485, 0], [0x420, 0], [0x421, 0], [0x50A, 0], [0x389, 0], [0x4A2, 0]]

  FWD_BLACKLISTED_ADDRS = {2: [0x340, 0x485, 0x420, 0x421, 0x50A, 0x389]}
  RELAY_MALFUNCTION_ADDRS = {0: (0x340, 0x485, 0x421, 0x420, 0x50A, 0x389)}  # LKAS11, LFAHDA_MFC, SCC12, SCC11, SCC13, SCC14

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(HyundaiSafetyFlagsSP.HAS_LDA_BUTTON)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.LONG | HyundaiSafetyFlags.CAMERA_SCC)
    self.safety.init_tests()

  def _accel_msg(self, accel, aeb_req=False, aeb_decel=0):
    values = {
      "aReqRaw": accel,
      "aReqValue": accel,
      "AEB_CmdAct": int(aeb_req),
      "CR_VSM_DecCmd": aeb_decel,
    }
    return self.packer.make_can_msg_safety("SCC12", self.SCC_BUS, values)

  def _tx_acc_state_msg(self, enable):
    values = {"MainMode_ACC": enable}
    return self.packer.make_can_msg_safety("SCC11", self.SCC_BUS, values)

  def test_no_aeb_scc12(self):
    self.assertTrue(self._tx(self._accel_msg(0)))
    self.assertFalse(self._tx(self._accel_msg(0, aeb_req=True)))
    self.assertFalse(self._tx(self._accel_msg(0, aeb_decel=1.0)))

  def test_tester_present_allowed(self):
    pass

  def test_disabled_ecu_alive(self):
    pass


@parameterized_class(LDA_BUTTON)
class TestHyundaiSafetyFCEVLong(TestHyundaiLongitudinalSafety, TestHyundaiSafetyFCEV):
  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiSafetyFCEVLong":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.FCEV_GAS | HyundaiSafetyFlags.LONG)
    self.safety.init_tests()


@parameterized_class(LDA_BUTTON)
class TestHyundaiLongitudinalESCCSafety(HyundaiLongitudinalBase, TestHyundaiSafety):
  TX_MSGS = [[0x340, 0], [0x4F1, 0], [0x485, 0], [0x420, 0], [0x421, 0], [0x50A, 0], [0x389, 0]]

  FWD_BLACKLISTED_ADDRS = {2: [0x340, 0x485, 0x420, 0x421, 0x50A, 0x389]}
  RELAY_MALFUNCTION_ADDRS = {0: (0x340, 0x485, 0x420, 0x421, 0x50A, 0x389)}  # LKAS11, LFAHDA_MFC, SCC12, SCC11, SCC13, SCC14

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiLongitudinalESCCSafety":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(HyundaiSafetyFlagsSP.ESCC | self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.LONG)
    self.safety.init_tests()

  def _accel_msg(self, accel, aeb_req=False, aeb_decel=0):
    values = {
      "aReqRaw": accel,
      "aReqValue": accel,
    }
    return self.packer.make_can_msg_safety("SCC12", self.SCC_BUS, values)

  def _tx_acc_state_msg(self, enable):
    values = {"MainMode_ACC": enable}
    return self.packer.make_can_msg_safety("SCC11", 0, values)

  def test_tester_present_allowed(self):
    pass

  def test_disabled_ecu_alive(self):
    pass


@parameterized_class(LDA_BUTTON)
class TestHyundaiNonSCCSafety(TestHyundaiSafety):

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiNonSCCSafety":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(HyundaiSafetyFlagsSP.NON_SCC | self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, 0)
    self.safety.init_tests()

  def _pcm_status_msg(self, enable):
    values = {"CRUISE_LAMP_S": enable, "AliveCounter": self.cnt_gas % 4}
    self.__class__.cnt_gas += 1
    return self.packer.make_can_msg_safety("EMS16", 0, values, fix_checksum=checksum)

  def _acc_state_msg(self, enable):
    values = {"CRUISE_LAMP_M": enable, "AliveCounter": self.cnt_gas % 4}
    self.__class__.cnt_gas += 1
    return self.packer.make_can_msg_safety("EMS16", 0, values, fix_checksum=checksum)

  def _user_gas_msg(self, gas: float, controls_allowed: bool = True):
    values = {"CF_Ems_AclAct": gas, "CRUISE_LAMP_M": 1, "CRUISE_LAMP_S": controls_allowed, "AliveCounter": self.cnt_gas % 4}
    self.__class__.cnt_gas += 1
    return self.packer.make_can_msg_safety("EMS16", 0, values, fix_checksum=checksum)

  def test_allow_engage_with_gas_pressed(self):
    self._rx(self._user_gas_msg(1, self.safety.get_controls_allowed()))
    self.safety.set_controls_allowed(True)
    self._rx(self._user_gas_msg(1, self.safety.get_controls_allowed()))
    self.assertTrue(self.safety.get_controls_allowed())
    self._rx(self._user_gas_msg(1, self.safety.get_controls_allowed()))
    self.assertTrue(self.safety.get_controls_allowed())

  def test_no_disengage_on_gas(self):
    self._rx(self._user_gas_msg(0, self.safety.get_controls_allowed()))
    self.safety.set_controls_allowed(True)
    self._rx(self._user_gas_msg(self.GAS_PRESSED_THRESHOLD + 1, self.safety.get_controls_allowed()))
    # Test we allow lateral, but not longitudinal
    self.assertTrue(self.safety.get_controls_allowed())
    self.assertFalse(self.safety.get_longitudinal_allowed())
    # Make sure we can re-gain longitudinal actuation
    self._rx(self._user_gas_msg(0, self.safety.get_controls_allowed()))
    self.assertTrue(self.safety.get_longitudinal_allowed())


@parameterized_class(ALL_NON_SCC_HEV_EV_COMBOS)
class TestHyundaiNonSCCSafety_HEV_EV(TestHyundaiSafety):

  PCM_STATUS_MSG = ("", "")
  ACC_STATE_MSG = ("", "")
  GAS_MSG = ("", "")
  SAFETY_PARAM = 0

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestHyundaiNonSCCSafety_HEV_EV":
      cls.safety = None
      raise unittest.SkipTest

  def setUp(self):
    self.packer = CANPackerSafety("hyundai_can_generated")
    self.safety = libsafety_py.libsafety
    self.safety.set_current_safety_param_sp(HyundaiSafetyFlagsSP.NON_SCC | self.SAFETY_PARAM_SP)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, self.SAFETY_PARAM)
    self.safety.init_tests()

  def _pcm_status_msg(self, enable):
    values = {self.PCM_STATUS_MSG[1]: enable}
    return self.packer.make_can_msg_safety(self.PCM_STATUS_MSG[0], 0, values)

  def _acc_state_msg(self, enable):
    values = {self.ACC_STATE_MSG[1]: enable}
    return self.packer.make_can_msg_safety(self.ACC_STATE_MSG[0], 0, values)

  def _user_gas_msg(self, gas):
    values = {self.GAS_MSG[1]: gas}
    return self.packer.make_can_msg_safety(self.GAS_MSG[0], 0, values, fix_checksum=checksum)


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
    self._configure_alt_standstill(longitudinal=True)

  def _configure_alt_standstill(self, longitudinal, enabled=True):
    safety_param = HyundaiSafetyFlags.HYBRID_GAS
    if longitudinal:
      safety_param |= HyundaiSafetyFlags.LONG
    if enabled:
      safety_param |= HyundaiSafetyFlags.ALT_STANDSTILL

    # set_safety_hooks consumes the SP param before init_tests resets its raw value.
    self.safety.set_current_safety_param_sp(HyundaiSafetyFlagsSP.DEFAULT)
    self.safety.set_safety_hooks(CarParams.SafetyModel.hyundai, safety_param)
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

  def _fixed_counter_tcs13_msg(self):
    values = {"DriverOverride": 0, "StandStill": 1, "AliveCounterTCS": 0}
    return self.packer.make_can_msg_safety("TCS13", 0, values, fix_checksum=checksum)

  def _prime_non_long_rx_config(self, omitted_address=None):
    messages = {
      0x371: self._user_gas_msg(0),
      0x386: self._whl_spd_bad_integrity_msg(),
      0x394: self.packer.make_can_msg_safety("TCS13", 0, {"AliveCounterTCS": 1}, fix_checksum=checksum),
      0x251: self._torque_driver_msg(0),
      0x4F1: self.packer.make_can_msg_safety("CLU11", 0, {"CF_Clu_AliveCnt1": 1}),
      0x420: self.packer.make_can_msg_safety("SCC11", 0, {"MainMode_ACC": 0}),
      0x421: self.packer.make_can_msg_safety("SCC12", 0, {"ACCMode": 0, "CR_VSM_Alive": 1}, fix_checksum=checksum),
    }
    for address, message in messages.items():
      if address != omitted_address:
        self.assertTrue(self._rx(message), f"RX rejected required address {address:#x}")

  def test_whl_spd_bad_integrity_allowed(self):
    # 0x386 lacks valid counter/checksum on this car; RX must NOT drop controls under ALT_STANDSTILL
    self.safety.set_controls_allowed(True)
    for _ in range(10):  # > MAX_WRONG_COUNTERS
      self.assertTrue(self._rx(self._whl_spd_bad_integrity_msg()))
      self.assertTrue(self.safety.get_controls_allowed())

  def test_whl_spd_bad_integrity_rejected_without_alt(self):
    for longitudinal in (True, False):
      with self.subTest(longitudinal=longitudinal):
        self._configure_alt_standstill(longitudinal=longitudinal, enabled=False)
        self.assertFalse(self._rx(self._whl_spd_bad_integrity_msg()))

  def test_tcs13_fixed_counter_rejected(self):
    expected_results = [True] * (common.MAX_WRONG_COUNTERS - 1) + [False]
    for longitudinal in (True, False):
      with self.subTest(longitudinal=longitudinal):
        self._configure_alt_standstill(longitudinal=longitudinal)
        results = [self._rx(self._fixed_counter_tcs13_msg()) for _ in range(common.MAX_WRONG_COUNTERS)]
        self.assertEqual(results, expected_results)

  def test_non_long_scc_rx_checks_are_independently_required(self):
    for omitted_address in (None, 0x420, 0x421):
      with self.subTest(omitted_address=omitted_address):
        self._configure_alt_standstill(longitudinal=False)
        self._prime_non_long_rx_config(omitted_address)
        self.assertEqual(self.safety.safety_config_valid(), omitted_address is None)

  def test_non_long_whl_spd_bad_integrity_allowed(self):
    # ALT_STANDSTILL is set per platform even when Alpha Long is off, so lateral-only safety must
    # also relax 0x386 while keeping TCS13 as the standstill/brake source.
    self._configure_alt_standstill(longitudinal=False)

    self.safety.set_controls_allowed(True)
    for _ in range(10):  # > MAX_WRONG_COUNTERS
      self.assertTrue(self._rx(self._whl_spd_bad_integrity_msg()))
      self.assertTrue(self.safety.get_controls_allowed())

    def bad_tcs13(msg):
      addr, dat, bus = checksum(msg)
      dat = bytearray(dat)
      dat[6] ^= 0x0F
      return addr, bytes(dat), bus
    msg = self.packer.make_can_msg_safety("TCS13", 0, {"AliveCounterTCS": 0}, fix_checksum=bad_tcs13)
    self.assertFalse(self._rx(msg))

  def test_tcs13_integrity_still_required(self):
    # 0x394 must stay strict: a bad checksum on TCS13 is rejected (not relaxed by ALT_STANDSTILL)
    def bad(msg):
      addr, dat, bus = checksum(msg)
      dat = bytearray(dat)
      dat[6] ^= 0x0F  # corrupt TCS13 checksum nibble
      return addr, bytes(dat), bus
    m = self.packer.make_can_msg_safety("TCS13", 0, {"AliveCounterTCS": 0}, fix_checksum=bad)
    self.assertFalse(self._rx(m))

  def test_vehicle_moving_from_tcs13(self):
    self._rx(self._vehicle_moving_msg(0.0))
    self.assertFalse(self.safety.get_vehicle_moving())      # StandStill=1 -> not moving
    self._rx(self._vehicle_moving_msg(self.STANDSTILL_THRESHOLD + 1))
    self.assertTrue(self.safety.get_vehicle_moving())       # StandStill=0 -> moving


if __name__ == "__main__":
  unittest.main()
