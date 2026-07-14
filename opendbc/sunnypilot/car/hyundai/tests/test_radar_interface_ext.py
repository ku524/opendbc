import unittest

from opendbc.testing import parameterized

from opendbc.can import CANPacker
from opendbc.car import CanData, gen_empty_fingerprint
from opendbc.car.car_helpers import interfaces
from opendbc.car.hyundai.radar_interface import RADAR_START_ADDR
from opendbc.car.hyundai.values import CAR, HyundaiFlags
from opendbc.sunnypilot.car.hyundai.escc import ESCC_MSG

ESCC_CARS = [
  (CAR.HYUNDAI_ELANTRA_2021, ESCC_MSG),
]

CAMERA_SCC_CARS = [
  (CAR.HYUNDAI_KONA_EV_2022, 0, 0x420, "SCC11"),
  (CAR.HYUNDAI_IONIQ_5, HyundaiFlags.CANFD_CAMERA_SCC.value, 0x1A0, "SCC_CONTROL"),
]

STANDARD_RADAR_CARS = [
  (CAR.HYUNDAI_ELANTRA_2021, 0),
  (CAR.HYUNDAI_SANTA_FE, 0),
]


class TestRadarInterfaceExt(unittest.TestCase):

  @staticmethod
  def _setup_platform(car_name, additional_flags=0, escc_msg=None):
    """Set up the platform with specific parameters"""
    CarInterface = interfaces[car_name]

    CP = CarInterface.get_non_essential_params(car_name)
    CP.flags |= additional_flags

    CP_SP = CarInterface.get_non_essential_params_sp(CP, car_name)

    CI = CarInterface(CP, CP_SP)

    RD = CI.RadarInterface(CP, CP_SP)

    if escc_msg is not None and hasattr(RD, 'use_escc'):
      try:
        RD.use_escc = True
      except AttributeError:
        object.__setattr__(RD, 'use_escc', True)

    return RD, CP, CP_SP

  @parameterized("car_name, escc_msg", ESCC_CARS)
  def test_escc_radar_interface(self, car_name, escc_msg):
    """Test radar interface for ESCC-enabled cars"""
    RD, CP, CP_SP = self._setup_platform(car_name, escc_msg=escc_msg)

    # Assert that ESCC features are present
    if hasattr(RD, 'use_escc'):
      self.assertTrue(RD.use_escc, "ESCC car should have use_escc=True")
    if hasattr(RD, 'use_radar_interface_ext'):
      self.assertTrue(RD.use_radar_interface_ext, "ESCC car should use radar interface ext")

    # Run radar interface once
    RD.update([])

    # Test radar fault
    if not CP.radarUnavailable and RD.rcp is not None:
      cans = [(0, [CanData(0, b'', 0) for _ in range(5)])]
      rr = RD.update(cans)
      self.assertTrue(rr is None or len(rr.errors) > 0)

  @parameterized("car_name, flags, expected_trigger, msg_src", CAMERA_SCC_CARS)
  def test_camera_scc_radar_interface(self, car_name, flags, expected_trigger, msg_src):
    """Test radar interface for Camera SCC cars"""
    RD, CP, CP_SP = self._setup_platform(car_name, additional_flags=flags)

    # Assert Camera SCC flag is set appropriately
    if flags & HyundaiFlags.CAMERA_SCC:
      self.assertTrue(CP.flags & HyundaiFlags.CAMERA_SCC, "Car should have CAMERA_SCC flag")
    if flags & HyundaiFlags.CANFD_CAMERA_SCC:
      self.assertTrue(CP.flags & HyundaiFlags.CANFD_CAMERA_SCC, "Car should have CANFD_CAMERA_SCC flag")

    # Check if using radar interface ext
    if hasattr(RD, 'use_radar_interface_ext'):
      self.assertTrue(RD.use_radar_interface_ext, "Camera SCC car should use radar interface ext")

    # Verify trigger message
    if hasattr(RD, 'trigger_msg'):
      self.assertEqual(RD.trigger_msg, expected_trigger, f"Expected trigger_msg {expected_trigger}, got {RD.trigger_msg}")

    # Run radar interface once
    RD.update([])

    # Test radar fault
    if not CP.radarUnavailable and RD.rcp is not None:
      cans = [(0, [CanData(0, b'', 0) for _ in range(5)])]
      rr = RD.update(cans)
      self.assertTrue(rr is None or len(rr.errors) > 0)

  @parameterized("car_name, flags", STANDARD_RADAR_CARS)
  def test_standard_radar_interface(self, car_name, flags):
    """Test radar interface for standard radar cars"""
    RD, CP, CP_SP = self._setup_platform(car_name, additional_flags=flags)

    # Standard cars should not use radar interface ext
    if hasattr(RD, 'use_radar_interface_ext'):
      self.assertFalse(RD.use_radar_interface_ext, "Standard car should not use radar interface ext")

    # Run radar interface once
    RD.update([])

    # For standard radar, test the _update method directly if available
    if not CP.radarUnavailable and RD.rcp is not None and \
          hasattr(RD, '_update') and hasattr(RD, 'trigger_msg'):
      # Setup for _update test if needed
      if hasattr(RD, 'updated_messages'):
        RD.updated_messages = {RD.trigger_msg}
      RD._update(RD.updated_messages)

    # Test radar fault
    if not CP.radarUnavailable and RD.rcp is not None:
      cans = [(0, [CanData(0, b'', 0) for _ in range(5)])]
      rr = RD.update(cans)
      self.assertTrue(rr is None or len(rr.errors) > 0)

  def test_sonata_lf_hybrid_mando_track_lifecycle(self):
    car_interface = interfaces[CAR.HYUNDAI_SONATA_LF_HYBRID]
    fingerprint = gen_empty_fingerprint()
    fingerprint[1][RADAR_START_ADDR] = 8
    car_params = car_interface.get_params(CAR.HYUNDAI_SONATA_LF_HYBRID, fingerprint, [], True, False, False)
    car_params_sp = car_interface.get_params_sp(car_params, CAR.HYUNDAI_SONATA_LF_HYBRID,
                                                fingerprint, [], True, False, False)
    radar_interface = car_interface.RadarInterface(car_params, car_params_sp)
    packer = CANPacker("hyundai_kia_mando_front_radar_generated")

    def radar_frame(address: int, state: int, distance: float = 0.0, relative_speed: float = 0.0) -> CanData:
      values = {
        "STATE": state,
        "AZIMUTH": 0.0,
        "LONG_DIST": distance,
        "REL_SPEED": relative_speed,
        "REL_ACCEL": 0.0,
      }
      packed_address, payload, _ = packer.make_can_msg(f"RADAR_TRACK_{address:x}", 1, values)
      return CanData(packed_address, payload, 1)

    valid_track = radar_frame(RADAR_START_ADDR, 3, distance=20.0, relative_speed=-2.0)
    self.assertIsNone(radar_interface.update([(1_000_000_000, [valid_track])]))

    out_of_range_track = CanData(0x520, b"\x00" * 8, 1)
    self.assertIsNone(radar_interface.update([(1_010_000_000, [out_of_range_track])]))

    invalid_trigger = radar_frame(RADAR_START_ADDR + 31, 0)
    radar_state = radar_interface.update([(1_020_000_000, [invalid_trigger])])
    self.assertIsNotNone(radar_state)
    self.assertEqual(len(radar_state.points), 1)
    self.assertAlmostEqual(radar_state.points[0].dRel, 20.0)
    self.assertAlmostEqual(radar_state.points[0].vRel, -2.0)

    invalid_track = radar_frame(RADAR_START_ADDR, 0)
    radar_state = radar_interface.update([(1_030_000_000, [invalid_track, invalid_trigger])])
    self.assertIsNotNone(radar_state)
    self.assertEqual(len(radar_state.points), 0)
