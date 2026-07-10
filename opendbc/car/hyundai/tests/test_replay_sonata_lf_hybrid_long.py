#!/usr/bin/env python3
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from opendbc.can import CANPacker
from opendbc.car import gen_empty_fingerprint
from opendbc.car.can_definitions import CanData
from opendbc.car.hyundai.tests import replay_sonata_lf_hybrid_long as replay


@dataclass(frozen=True)
class CanEvent:
  logMonoTime: int
  can: tuple[CanData, ...]


class TestReplayInputValidation(unittest.TestCase):
  def setUp(self):
    self.directory_context = TemporaryDirectory()
    self.directory = Path(self.directory_context.name)

  def tearDown(self):
    self.directory_context.cleanup()

  def segment_path(self, segment: int, route_file_prefix: str = replay.ROUTE_FILE_PREFIX) -> Path:
    path = self.directory / f"{route_file_prefix}--{segment}--rlog.zst"
    path.touch()
    return path

  def test_exact_route_segments_accepted(self):
    paths = [self.segment_path(segment) for segment in (3, 0, 2)]
    segments = replay.validate_segment_paths([str(path) for path in paths])
    self.assertEqual([segment.index for segment in segments], [0, 2, 3])

  def test_wrong_segment_sets_rejected(self):
    cases = (
      [],
      [self.segment_path(0)],
      [self.segment_path(segment) for segment in (0, 1, 2)],
      [self.segment_path(segment) for segment in (0, 2, 3, 4)],
    )
    for paths in cases:
      with self.subTest(paths=paths), self.assertRaises(replay.ReplayValidationError):
        replay.validate_segment_paths([str(path) for path in paths])

  def test_duplicate_and_other_route_rejected(self):
    segment_zero = self.segment_path(0)
    duplicate_paths = [segment_zero, segment_zero, self.segment_path(3)]
    with self.assertRaises(replay.ReplayValidationError):
      replay.validate_segment_paths([str(path) for path in duplicate_paths])

    other_route = "0000000000000000_00000000--0000000000"
    paths = [self.segment_path(0, other_route), self.segment_path(2), self.segment_path(3)]
    with self.assertRaises(replay.ReplayValidationError):
      replay.validate_segment_paths([str(path) for path in paths])

  def test_dev_null_fails_under_optimization(self):
    command = [sys.executable, "-O", str(Path(replay.__file__)), "/dev/null"]
    completed = subprocess.run(command, capture_output=True, check=False, text=True)
    self.assertNotEqual(completed.returncode, 0)
    self.assertNotIn("ALL OFFLINE CHECKS PASSED", completed.stdout)

  def test_named_empty_rlogs_fail_under_optimization(self):
    paths = [self.segment_path(segment) for segment in (0, 2, 3)]
    command = [sys.executable, "-O", str(Path(replay.__file__)), *(str(path) for path in paths)]
    completed = subprocess.run(command, capture_output=True, check=False, text=True)
    self.assertNotEqual(completed.returncode, 0)
    self.assertNotIn("ALL OFFLINE CHECKS PASSED", completed.stdout)


class TestFreshStandstillPairing(unittest.TestCase):
  def setUp(self):
    self.packer = CANPacker("hyundai_can_generated")

  def wheel_speed_frame(self, speed_kph: float) -> CanData:
    values = {f"WHL_SPD_{corner}": speed_kph for corner in ("FL", "FR", "RL", "RR")}
    address, payload, bus = self.packer.make_can_msg("WHL_SPD11", 0, values)
    return CanData(address, payload, bus)

  def tcs13_frame(self, standstill: bool) -> CanData:
    address, payload, bus = self.packer.make_can_msg("TCS13", 0, {"StandStill": int(standstill)})
    return CanData(address, payload, bus)

  def test_only_fresh_tcs13_wheel_pairs_are_counted(self):
    millisecond = 1_000_000
    events = (
      CanEvent(0, (self.tcs13_frame(True),)),
      CanEvent(10 * millisecond, (self.wheel_speed_frame(0.0),)),
      CanEvent(20 * millisecond, (CanData(0x123, b"\x00" * 8, 0),)),
      CanEvent(30 * millisecond, (self.tcs13_frame(True),)),
      CanEvent(200 * millisecond, (self.tcs13_frame(True),)),
      CanEvent(210 * millisecond, (self.wheel_speed_frame(0.3), self.tcs13_frame(True))),
      CanEvent(220 * millisecond, (self.wheel_speed_frame(6.0), self.tcs13_frame(False))),
    )

    stats = replay.collect_standstill_stats(events, maximum_pair_skew_nanos=100 * millisecond)

    self.assertEqual(stats.stopped_matches, 1)
    self.assertEqual(stats.stopped_samples, 1)
    self.assertEqual(stats.moving_matches, 1)
    self.assertEqual(stats.moving_samples, 1)
    self.assertEqual(stats.neutral_samples, 1)
    self.assertEqual(stats.unpaired_samples, 2)


class TestCaptureValidation(unittest.TestCase):
  def loaded_segment(self, events: tuple[CanEvent, ...], duration_seconds: float = 1.0) -> replay.LoadedSegment:
    source = replay.SegmentPath(Path("capture--0--rlog.zst"), 0)
    return replay.LoadedSegment(source, events, duration_seconds)

  def test_address_metrics_reject_wrong_bus_and_length(self):
    requirement = replay.AddressRequirement(0x371, 1.0)
    wrong_bus = self.loaded_segment((CanEvent(0, (CanData(0x371, b"\x00" * 8, 1),)),))
    with self.assertRaises(replay.ReplayValidationError):
      replay.address_metrics(wrong_bus, requirement)

    wrong_length = self.loaded_segment((CanEvent(0, (CanData(0x371, b"\x00" * 7, 0),)),))
    with self.assertRaises(replay.ReplayValidationError):
      replay.address_metrics(wrong_length, requirement)

  def test_address_metrics_report_frequency_and_gap(self):
    events = (
      CanEvent(0, (CanData(0x371, b"\x00" * 8, 0),)),
      CanEvent(500_000_000, (CanData(0x371, b"\x00" * 8, 0),)),
    )
    metrics = replay.address_metrics(self.loaded_segment(events), replay.AddressRequirement(0x371, 1.0))
    self.assertEqual(metrics.count, 2)
    self.assertEqual(metrics.observed_frequency_hz, 2.0)
    self.assertEqual(metrics.maximum_gap_seconds, 0.5)

  def test_capture_fingerprint_auto_flags_are_rejected(self):
    for forbidden_address in (0x2AB, 0x391, 0x38D):
      with self.subTest(forbidden_address=forbidden_address):
        fingerprint = gen_empty_fingerprint()
        fingerprint[0][forbidden_address] = 8
        with self.assertRaises(replay.ReplayValidationError):
          replay.check_params(fingerprint)


if __name__ == "__main__":
  unittest.main()
