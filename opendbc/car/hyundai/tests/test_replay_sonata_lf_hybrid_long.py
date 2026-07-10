#!/usr/bin/env python3
from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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
    path.write_bytes(f"segment-{segment}".encode())
    return path

  @staticmethod
  def expected_hashes(paths: list[Path]) -> dict[int, str]:
    return {
      int(path.name.split("--")[-2]): hashlib.sha256(path.read_bytes()).hexdigest()
      for path in paths
    }

  def test_exact_route_segments_accepted(self):
    paths = [self.segment_path(segment) for segment in (3, 0, 2)]
    segments = replay.validate_segment_paths([str(path) for path in paths], self.expected_hashes(paths))
    self.assertEqual([segment.index for segment in segments], [0, 2, 3])

  def test_duplicate_content_and_swapped_content_rejected(self):
    paths = [self.segment_path(segment) for segment in (0, 2, 3)]
    expected_hashes = self.expected_hashes(paths)

    paths[2].write_bytes(paths[1].read_bytes())
    with self.assertRaisesRegex(replay.ReplayValidationError, "duplicate segment content"):
      replay.validate_segment_paths([str(path) for path in paths], expected_hashes)

    paths[1].write_bytes(b"segment-3")
    paths[2].write_bytes(b"segment-2")
    with self.assertRaisesRegex(replay.ReplayValidationError, "SHA-256"):
      replay.validate_segment_paths([str(path) for path in paths], expected_hashes)

  def test_decode_uses_authenticated_content_snapshot(self):
    paths = [self.segment_path(segment) for segment in (0, 2, 3)]
    segments = replay.validate_segment_paths([str(path) for path in paths], self.expected_hashes(paths))
    authenticated_content = paths[0].read_bytes()
    paths[0].write_bytes(b"replacement-after-validation")
    decoded_content: list[bytes] = []

    def capture_snapshot(snapshot_path: str, **_kwargs):
      decoded_content.append(Path(snapshot_path).read_bytes())
      return ()

    with patch.object(replay, "LogReader", side_effect=capture_snapshot):
      with self.assertRaises(replay.ReplayValidationError):
        replay.load_segments(segments[:1])

    self.assertEqual(decoded_content, [authenticated_content])

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

  def tcs13_frame(self, standstill: bool, counter: int = 0) -> CanData:
    address, payload, bus = self.packer.make_can_msg("TCS13", 0, {"StandStill": int(standstill)})
    mutable_payload = bytearray(payload)
    mutable_payload[1] = (mutable_payload[1] & 0x1F) | (counter << 5)
    mutable_payload[6] &= 0xF0
    mutable_payload[6] |= replay.compute_tcs13_checksum(mutable_payload)
    return CanData(address, bytes(mutable_payload), bus)

  @staticmethod
  def loaded_segment(events: tuple[CanEvent, ...], index: int = 0) -> replay.LoadedSegment:
    source = replay.SegmentPath(Path(f"capture--{index}--rlog.zst"), index)
    duration_seconds = (events[-1].logMonoTime - events[0].logMonoTime) / replay.NANOSECONDS_PER_SECOND if len(events) > 1 else 0.0
    return replay.LoadedSegment(source, events, duration_seconds)

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

    stats = replay.collect_standstill_stats((self.loaded_segment(events),), maximum_pair_skew_nanos=100 * millisecond)

    self.assertEqual(stats.stopped_matches, 1)
    self.assertEqual(stats.stopped_samples, 1)
    self.assertEqual(stats.moving_matches, 1)
    self.assertEqual(stats.moving_samples, 1)
    self.assertEqual(stats.neutral_samples, 1)
    self.assertEqual(stats.unpaired_samples, 2)

  def test_frame_order_does_not_change_pairing(self):
    wheel_frame = self.wheel_speed_frame(6.0)
    tcs_frame = self.tcs13_frame(False)
    forward = (CanEvent(0, (wheel_frame, tcs_frame)),)
    reversed_frames = (CanEvent(0, (tcs_frame, wheel_frame)),)

    forward_stats = replay.collect_standstill_stats((self.loaded_segment(forward),), replay.MAXIMUM_PAIR_SKEW_NANOS)
    reversed_stats = replay.collect_standstill_stats((self.loaded_segment(reversed_frames),), replay.MAXIMUM_PAIR_SKEW_NANOS)

    self.assertEqual(forward_stats, reversed_stats)
    self.assertEqual(forward_stats.moving_matches, 1)

  def test_negative_skew_is_rejected(self):
    events = (
      CanEvent(100_000_000, (self.wheel_speed_frame(6.0),)),
      CanEvent(0, (self.tcs13_frame(False),)),
    )
    with self.assertRaisesRegex(replay.ReplayValidationError, "negative wheel/TCS13 skew"):
      replay.collect_standstill_stats((self.loaded_segment(events),), replay.MAXIMUM_PAIR_SKEW_NANOS)

  def test_wheel_state_does_not_cross_segment_boundary(self):
    wheel_segment = self.loaded_segment((CanEvent(0, (self.wheel_speed_frame(0.0),)),), index=0)
    tcs_segment = self.loaded_segment((CanEvent(10_000_000, (self.tcs13_frame(True),)),), index=2)

    stats = replay.collect_standstill_stats((wheel_segment, tcs_segment), replay.MAXIMUM_PAIR_SKEW_NANOS)

    self.assertEqual(stats.stopped_samples, 0)
    self.assertEqual(stats.unpaired_samples, 1)

  def test_same_timestamp_events_are_one_sample(self):
    events = (
      CanEvent(0, (self.wheel_speed_frame(6.0),)),
      CanEvent(0, (self.tcs13_frame(False, counter=1),)),
      CanEvent(0, (self.tcs13_frame(False, counter=2),)),
    )

    stats = replay.collect_standstill_stats((self.loaded_segment(events),), replay.MAXIMUM_PAIR_SKEW_NANOS)

    self.assertEqual(stats.moving_matches, 1)
    self.assertEqual(stats.moving_samples, 1)


class TestTcs13Integrity(unittest.TestCase):
  CANONICAL_PAYLOADS = (
    bytes.fromhex("8ec400008e241d83"),
    bytes.fromhex("49e4000049241d83"),
    bytes.fromhex("5c0400005c241383"),
    bytes.fromhex("ad240000ad241583"),
    bytes.fromhex("6f4400006f241783"),
    bytes.fromhex("3364000033241383"),
    bytes.fromhex("8384000083241783"),
    bytes.fromhex("7ba400007b241783"),
  )

  def setUp(self):
    self.pairing = TestFreshStandstillPairing()
    self.pairing.setUp()

  def segment(self, counters: tuple[int, ...], index: int = 0) -> replay.LoadedSegment:
    events = tuple(CanEvent(frame_index * 20_000_000, (self.pairing.tcs13_frame(True, counter),))
                   for frame_index, counter in enumerate(counters))
    return self.pairing.loaded_segment(events, index)

  def canonical_segment(self, index: int = 0, frame_count: int = len(CANONICAL_PAYLOADS)) -> replay.LoadedSegment:
    events = tuple(CanEvent(frame_index * 20_000_000, (CanData(0x394, payload, 0),))
                   for frame_index, payload in enumerate(self.CANONICAL_PAYLOADS[:frame_count]))
    return self.pairing.loaded_segment(events, index)

  def test_checksum_matches_canonical_payloads(self):
    expected_checksums = (13, 13, 3, 5, 7, 3, 7, 7)
    self.assertEqual(tuple(replay.compute_tcs13_checksum(payload) for payload in self.CANONICAL_PAYLOADS), expected_checksums)

  def test_valid_counter_wrap_and_segment_reset(self):
    replay.validate_tcs13_integrity((self.canonical_segment(), self.canonical_segment(index=2, frame_count=2)))

  def test_bad_checksum_is_rejected(self):
    frame = self.pairing.tcs13_frame(True, 1)
    corrupted_payload = bytearray(frame.dat)
    corrupted_payload[6] ^= 1
    segment = self.pairing.loaded_segment((CanEvent(0, (CanData(frame.address, bytes(corrupted_payload), frame.src),)),))

    with self.assertRaisesRegex(replay.ReplayValidationError, "checksum"):
      replay.validate_tcs13_integrity((segment,))

  def test_fixed_counter_is_rejected_at_safety_limit(self):
    with self.assertRaisesRegex(replay.ReplayValidationError, "counter"):
      replay.validate_tcs13_integrity((self.segment((0, 0, 0, 0, 0)),))


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
      CanEvent(0, (CanData(0x123, b"\x00" * 8, 0),)),
      CanEvent(200_000_000, (CanData(0x371, b"\x00" * 8, 0), CanData(0x371, b"\x01" * 8, 0))),
      CanEvent(400_000_000, (CanData(0x371, b"\x02" * 8, 0),)),
      CanEvent(1_000_000_000, (CanData(0x123, b"\x00" * 8, 0),)),
    )
    metrics = replay.address_metrics(self.loaded_segment(events), replay.AddressRequirement(0x371, 1.0))
    self.assertEqual(metrics.count, 2)
    self.assertEqual(metrics.observed_frequency_hz, 2.0)
    self.assertEqual(metrics.maximum_gap_seconds, 0.6)

  def test_canonical_address_definitions(self):
    requirements = {requirement.address: requirement for requirement in replay.REQUIRED_BUS_ZERO_ADDRESSES}
    self.assertEqual(requirements[0x386].expected_frequency_hz, 50.0)
    self.assertEqual(requirements[0x394].expected_frequency_hz, 50.0)
    self.assertEqual(requirements[0x4F1].expected_length, 4)

  def test_segment_ranges_must_be_ordered_and_nonoverlapping(self):
    first = self.loaded_segment((CanEvent(0, (CanData(0x123, b"\x00" * 8, 0),)),
                                 CanEvent(20, (CanData(0x123, b"\x00" * 8, 0),))))
    overlapping = replay.LoadedSegment(replay.SegmentPath(Path("capture--2--rlog.zst"), 2),
                                       (CanEvent(10, (CanData(0x123, b"\x00" * 8, 0),)),
                                        CanEvent(30, (CanData(0x123, b"\x00" * 8, 0),))), 0.0)
    with self.assertRaisesRegex(replay.ReplayValidationError, "overlaps"):
      replay.validate_segment_timeline((first, overlapping))

  def test_raw_event_timestamp_regression_is_rejected(self):
    events = (
      CanEvent(20, (CanData(0x123, b"\x00" * 8, 0),)),
      CanEvent(10, (CanData(0x123, b"\x00" * 8, 0),)),
    )
    with self.assertRaisesRegex(replay.ReplayValidationError, "not monotonic"):
      replay.validate_event_timestamp_order(events, segment_index=0)

  def test_capture_fingerprint_auto_flags_are_rejected(self):
    valid_fingerprint = gen_empty_fingerprint()
    valid_fingerprint[0][0x544] = 8
    valid_fingerprint[2][0x53E] = 8
    replay.check_params(valid_fingerprint)

    cases = (
      (0x2AB, 0, "unexpected SP flags"),
      (0x391, 0, "unexpected LDA or FCA flag"),
      (0x38D, 0, "unexpected LDA or FCA flag"),
      (0x38D, 2, "unexpected LDA or FCA flag"),
    )
    for forbidden_address, bus, error_pattern in cases:
      with self.subTest(forbidden_address=forbidden_address, bus=bus):
        fingerprint = gen_empty_fingerprint()
        fingerprint[0][0x544] = 8
        fingerprint[2][0x53E] = 8
        fingerprint[bus][forbidden_address] = 8
        with self.assertRaisesRegex(replay.ReplayValidationError, error_pattern):
          replay.check_params(fingerprint)


if __name__ == "__main__":
  unittest.main()
