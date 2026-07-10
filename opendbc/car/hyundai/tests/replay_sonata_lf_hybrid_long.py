#!/usr/bin/env python3
"""Fail-closed offline replay for CAR.HYUNDAI_SONATA_LF_HYBRID.

The capture filename and CAN signature identify the expected route structure. Cryptographic route
identity still requires SHA-256 values from the owner's canonical files. This replay validates RX
and interface plumbing only; actuation and radar disable remain on-car gates.
"""
from collections.abc import Sequence
from dataclasses import dataclass
import math
from pathlib import Path
import re
import sys
from typing import Protocol, cast
import warnings

from opendbc.can.parser import CANParser
from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.can_definitions import CanData
from opendbc.car.car_helpers import interfaces
from opendbc.car.hyundai.values import CAR, HyundaiFlags, HyundaiSafetyFlags
from opendbc.car.interfaces import CarInterfaceBase
from opendbc.car.logreader import LogReader
from opendbc.sunnypilot.car.hyundai.values import HyundaiFlagsSP, HyundaiSafetyFlagsSP

PLATFORM = CAR.HYUNDAI_SONATA_LF_HYBRID
ROUTE_FILE_PREFIX = "9f9b411a57b8ce21_00000001--d6d081f0e7"
EXPECTED_SEGMENT_INDICES = frozenset({0, 2, 3})
SEGMENT_FILENAME_PATTERN = re.compile(rf"^{re.escape(ROUTE_FILE_PREFIX)}--(?P<segment>\d+)--rlog\.zst$")
DEFAULT_SEGMENT_PATHS = tuple(
  f"/Users/mark.yeon/Downloads/{ROUTE_FILE_PREFIX}--{segment}--rlog.zst"
  for segment in sorted(EXPECTED_SEGMENT_INDICES)
)

NANOSECONDS_PER_SECOND = 1_000_000_000
WARMUP_NANOS = NANOSECONDS_PER_SECOND  # FRAME_FINGERPRINT=100 is documented as one second.
MINIMUM_SEGMENT_DURATION_SECONDS = 30.0
MINIMUM_CAN_EVENTS_PER_SEGMENT = 5_000
MINIMUM_TOTAL_CAN_EVENTS = 18_000  # Canonical replay recorded 18,121 CAN events.
MAXIMUM_FREQUENCY_GAP_CYCLES = 10
MINIMUM_FREQUENCY_RATIO = 0.5
MAXIMUM_PAIR_SKEW_NANOS = 100_000_000  # Ten cycles at the declared 100 Hz safety rate.
MINIMUM_STOPPED_SAMPLES = 3_000
MINIMUM_MOVING_SAMPLES = 5_000
MINIMUM_POLARITY_RATIO = 0.9


class ReplayValidationError(RuntimeError):
  pass


class RecordedCanFrame(Protocol):
  address: int
  dat: bytes
  src: int


class RecordedCanEvent(Protocol):
  logMonoTime: int
  can: Sequence[RecordedCanFrame]


@dataclass(frozen=True)
class SegmentPath:
  path: Path
  index: int


@dataclass(frozen=True)
class LoadedSegment:
  source: SegmentPath
  events: tuple[RecordedCanEvent, ...]
  duration_seconds: float


@dataclass(frozen=True)
class AddressRequirement:
  address: int
  expected_frequency_hz: float
  expected_length: int = 8


@dataclass(frozen=True)
class AddressMetrics:
  count: int
  observed_frequency_hz: float
  maximum_gap_seconds: float


@dataclass(frozen=True)
class StandstillStats:
  stopped_matches: int = 0
  stopped_samples: int = 0
  moving_matches: int = 0
  moving_samples: int = 0
  neutral_samples: int = 0
  unpaired_samples: int = 0


REQUIRED_BUS_ZERO_ADDRESSES = (
  AddressRequirement(0x251, 50.0),
  AddressRequirement(0x371, 100.0),
  AddressRequirement(0x372, 1.0),  # ELECT_GEAR has no declared rate; CANParser's default is 1 Hz.
  AddressRequirement(0x386, 100.0),
  AddressRequirement(0x394, 100.0),
  AddressRequirement(0x420, 50.0),
  AddressRequirement(0x421, 50.0),
  AddressRequirement(0x4F1, 50.0),
)
FORBIDDEN_ADDRESS_BUSES = {
  0x2AB: frozenset({0}),     # ESCC
  0x391: frozenset({0}),     # LDA button
  0x38D: frozenset({0, 2}),  # FCA11 auto-detection
}


def require(condition: bool, message: str) -> None:
  if not condition:
    raise ReplayValidationError(message)


def validate_segment_paths(paths: Sequence[str]) -> tuple[SegmentPath, ...]:
  require(len(paths) == len(EXPECTED_SEGMENT_INDICES),
          f"expected exactly three segments {sorted(EXPECTED_SEGMENT_INDICES)}, got {len(paths)}")

  segments: list[SegmentPath] = []
  resolved_paths: set[Path] = set()
  file_identities: set[tuple[int, int]] = set()
  for raw_path in paths:
    path = Path(raw_path).expanduser()
    match = SEGMENT_FILENAME_PATTERN.fullmatch(path.name)
    require(match is not None, f"unexpected route segment filename: {path.name}")

    segment_index = int(match.group("segment"))
    require(segment_index in EXPECTED_SEGMENT_INDICES, f"unexpected segment index: {segment_index}")
    require(path.exists() and path.is_file(), f"segment is not a regular file: {path}")

    resolved_path = path.resolve()
    file_stat = resolved_path.stat()
    file_identity = (file_stat.st_dev, file_stat.st_ino)
    require(resolved_path not in resolved_paths, f"duplicate segment path: {resolved_path}")
    require(file_identity not in file_identities, f"duplicate segment file: {resolved_path}")
    resolved_paths.add(resolved_path)
    file_identities.add(file_identity)
    segments.append(SegmentPath(resolved_path, segment_index))

  actual_indices = {segment.index for segment in segments}
  require(actual_indices == EXPECTED_SEGMENT_INDICES,
          f"expected segments {sorted(EXPECTED_SEGMENT_INDICES)}, got {sorted(actual_indices)}")
  return tuple(sorted(segments, key=lambda segment: segment.index))


def load_segments(segment_paths: Sequence[SegmentPath]) -> tuple[LoadedSegment, ...]:
  loaded_segments: list[LoadedSegment] = []
  for source in segment_paths:
    with warnings.catch_warnings():
      warnings.simplefilter("error", RuntimeWarning)
      messages = LogReader(str(source.path), only_union_types=True, sort_by_time=True)
      events = tuple(cast(RecordedCanEvent, message) for message in messages if message.which() == "can")

    require(len(events) >= MINIMUM_CAN_EVENTS_PER_SEGMENT,
            f"segment {source.index} has only {len(events)} CAN events; expected at least {MINIMUM_CAN_EVENTS_PER_SEGMENT}")
    require(all(len(event.can) > 0 for event in events), f"segment {source.index} contains an empty CAN event")

    timestamps = [event.logMonoTime for event in events]
    require(all(current >= previous for previous, current in zip(timestamps, timestamps[1:], strict=False)),
            f"segment {source.index} CAN timestamps are not monotonic")
    duration_seconds = (timestamps[-1] - timestamps[0]) / NANOSECONDS_PER_SECOND
    require(duration_seconds >= MINIMUM_SEGMENT_DURATION_SECONDS,
            f"segment {source.index} duration {duration_seconds:.1f}s is below {MINIMUM_SEGMENT_DURATION_SECONDS:.1f}s")

    print(f"  segment {source.index}: {len(events)} CAN events, {duration_seconds:.1f}s")
    loaded_segments.append(LoadedSegment(source, events, duration_seconds))

  total_events = sum(len(segment.events) for segment in loaded_segments)
  require(total_events >= MINIMUM_TOTAL_CAN_EVENTS,
          f"capture has only {total_events} CAN events; expected at least {MINIMUM_TOTAL_CAN_EVENTS}")
  return tuple(loaded_segments)


def address_metrics(segment: LoadedSegment, requirement: AddressRequirement) -> AddressMetrics:
  timestamps: list[int] = []
  wrong_lengths: list[int] = []
  for event in segment.events:
    for frame in event.can:
      if frame.src == 0 and frame.address == requirement.address:
        frame_length = len(bytes(frame.dat))
        if frame_length == requirement.expected_length:
          timestamps.append(event.logMonoTime)
        else:
          wrong_lengths.append(frame_length)

  require(not wrong_lengths,
          f"segment {segment.source.index} address {requirement.address:#x} has wrong lengths {sorted(set(wrong_lengths))}")
  require(timestamps, f"segment {segment.source.index} missing bus-0 address {requirement.address:#x}")

  maximum_gap_seconds = max(
    ((current - previous) / NANOSECONDS_PER_SECOND for previous, current in zip(timestamps, timestamps[1:], strict=False)),
    default=segment.duration_seconds,
  )
  return AddressMetrics(
    count=len(timestamps),
    observed_frequency_hz=len(timestamps) / segment.duration_seconds,
    maximum_gap_seconds=maximum_gap_seconds,
  )


def validate_capture(segments: Sequence[LoadedSegment]) -> dict[int, dict[int, int]]:
  fingerprint = gen_empty_fingerprint()
  for segment in segments:
    for requirement in REQUIRED_BUS_ZERO_ADDRESSES:
      metrics = address_metrics(segment, requirement)
      minimum_frequency = requirement.expected_frequency_hz * MINIMUM_FREQUENCY_RATIO
      maximum_gap = MAXIMUM_FREQUENCY_GAP_CYCLES / requirement.expected_frequency_hz
      require(metrics.observed_frequency_hz >= minimum_frequency,
              "".join((f"segment {segment.source.index} address {requirement.address:#x} rate ",
                       f"{metrics.observed_frequency_hz:.1f} Hz is below {minimum_frequency:.1f} Hz")))
      require(metrics.maximum_gap_seconds <= maximum_gap,
              "".join((f"segment {segment.source.index} address {requirement.address:#x} max gap ",
                       f"{metrics.maximum_gap_seconds:.3f}s exceeds {maximum_gap:.3f}s")))
      print("".join((f"    {requirement.address:#05x}: {metrics.count} frames, ",
                     f"{metrics.observed_frequency_hz:.1f} Hz, max gap {metrics.maximum_gap_seconds * 1_000:.1f}ms")))

    for event in segment.events:
      for frame in event.can:
        forbidden_buses = FORBIDDEN_ADDRESS_BUSES.get(frame.address)
        require(forbidden_buses is None or frame.src not in forbidden_buses,
                f"forbidden address {frame.address:#x} present on bus {frame.src} in segment {segment.source.index}")
        if frame.src in fingerprint:
          fingerprint[frame.src][frame.address] = len(bytes(frame.dat))

  return fingerprint


def check_params(fingerprint: dict[int, dict[int, int]]) -> tuple[structs.CarParams, structs.CarParamsSP, type[CarInterfaceBase]]:
  car_interface = interfaces[PLATFORM]
  car_params = car_interface.get_params(PLATFORM, fingerprint, [], alpha_long=True, is_release=False, docs=False)
  car_params_sp = car_interface.get_params_sp(car_params, PLATFORM, fingerprint, [], alpha_long=True, is_release_sp=False, docs=False)

  require(car_params.openpilotLongitudinalControl, "openpilotLongitudinalControl is False")
  require(car_params.safetyConfigs[-1].safetyModel == structs.CarParams.SafetyModel.hyundai, "not on Hyundai safety")
  safety_param = car_params.safetyConfigs[-1].safetyParam
  for safety_flag in (HyundaiSafetyFlags.LONG, HyundaiSafetyFlags.HYBRID_GAS, HyundaiSafetyFlags.ALT_STANDSTILL):
    require(bool(safety_param & safety_flag.value), f"safetyParam missing {safety_flag.name}")

  require(not car_params.flags & (HyundaiFlags.HAS_LDA_BUTTON | HyundaiFlags.USE_FCA), "unexpected LDA or FCA flag")
  require(not car_params_sp.flags & HyundaiFlagsSP.ENHANCED_SCC, "unexpected ENHANCED_SCC flag")
  require(not car_params_sp.safetyParam & (HyundaiSafetyFlagsSP.ESCC | HyundaiSafetyFlagsSP.NON_SCC),
          "unexpected ESCC or NON_SCC safety param")
  print("  CarParams OK: Hyundai safety, long ON, LONG|HYBRID_GAS|ALT_STANDSTILL, SP auto-flags off")
  return car_params, car_params_sp, car_interface


def replay_state(car_params: structs.CarParams, car_params_sp: structs.CarParamsSP,
                 car_interface: type[CarInterfaceBase], segments: Sequence[LoadedSegment]) -> None:
  car_control = structs.CarControl().as_reader()
  car_control_sp = structs.CarControlSP()
  maximum_speed = 0.0
  replayed_frames = 0

  for segment in segments:
    replay_interface = car_interface(car_params, car_params_sp)
    first_timestamp = segment.events[0].logMonoTime
    post_warmup_frames = 0
    for event in segment.events:
      frames = [CanData(frame.address, bytes(frame.dat), frame.src) for frame in event.can]
      car_state, _ = replay_interface.update([(event.logMonoTime, frames)])
      replay_interface.apply(car_control, car_control_sp, event.logMonoTime)
      require(math.isfinite(car_state.vEgo) and -1.0 <= car_state.vEgo <= 80.0, f"vEgo out of range: {car_state.vEgo}")
      maximum_speed = max(maximum_speed, car_state.vEgo)
      replayed_frames += 1

      if event.logMonoTime - first_timestamp >= WARMUP_NANOS:
        require(car_state.canValid, f"segment {segment.source.index} canValid=False after warm-up")
        require(not car_state.canTimeout, f"segment {segment.source.index} canTimeout=True after warm-up")
        post_warmup_frames += 1

    require(post_warmup_frames > 0, f"segment {segment.source.index} has no post-warm-up states")

  print(f"  replayed {replayed_frames} frames without error; max vEgo={maximum_speed * 3.6:.1f} km/h")


def collect_standstill_stats(can_events: Sequence[RecordedCanEvent], maximum_pair_skew_nanos: int) -> StandstillStats:
  can_parser = CANParser("hyundai_can_generated", [("TCS13", 0), ("WHL_SPD11", 0)], 0)
  latest_wheel_timestamp: int | None = None
  latest_wheel_speed: float | None = None
  stopped_matches = stopped_samples = moving_matches = moving_samples = neutral_samples = unpaired_samples = 0

  for event in can_events:
    for frame in event.can:
      if frame.src != 0 or frame.address not in (0x386, 0x394):
        continue

      updated_addresses = can_parser.update((event.logMonoTime, [(frame.address, bytes(frame.dat), frame.src)]))
      if 0x386 in updated_addresses:
        wheel_speeds = can_parser.vl["WHL_SPD11"]
        latest_wheel_speed = (
          wheel_speeds["WHL_SPD_FL"] + wheel_speeds["WHL_SPD_FR"] +
          wheel_speeds["WHL_SPD_RL"] + wheel_speeds["WHL_SPD_RR"]
        ) / 4.0
        latest_wheel_timestamp = event.logMonoTime

      if 0x394 not in updated_addresses:
        continue
      if latest_wheel_timestamp is None or latest_wheel_speed is None or \
         event.logMonoTime - latest_wheel_timestamp > maximum_pair_skew_nanos:
        unpaired_samples += 1
        continue

      standstill = int(round(can_parser.vl["TCS13"]["StandStill"]))
      if latest_wheel_speed < 0.3:
        stopped_samples += 1
        stopped_matches += standstill == 1
      elif latest_wheel_speed > 5.0:
        moving_samples += 1
        moving_matches += standstill == 0
      else:
        neutral_samples += 1

  return StandstillStats(stopped_matches, stopped_samples, moving_matches, moving_samples, neutral_samples, unpaired_samples)


def check_standstill_polarity(segments: Sequence[LoadedSegment]) -> None:
  can_events = tuple(event for segment in segments for event in segment.events)
  stats = collect_standstill_stats(can_events, MAXIMUM_PAIR_SKEW_NANOS)
  require(stats.stopped_samples >= MINIMUM_STOPPED_SAMPLES,
          f"only {stats.stopped_samples} fresh stopped samples; expected at least {MINIMUM_STOPPED_SAMPLES}")
  require(stats.moving_samples >= MINIMUM_MOVING_SAMPLES,
          f"only {stats.moving_samples} fresh moving samples; expected at least {MINIMUM_MOVING_SAMPLES}")

  stopped_ratio = stats.stopped_matches / stats.stopped_samples
  moving_ratio = stats.moving_matches / stats.moving_samples
  print("".join((f"  StandStill fresh pairs: stopped->1 {stats.stopped_matches}/{stats.stopped_samples} ",
                 f"({100 * stopped_ratio:.2f}%), moving->0 {stats.moving_matches}/{stats.moving_samples} ",
                 f"({100 * moving_ratio:.2f}%), neutral={stats.neutral_samples}, unpaired={stats.unpaired_samples}")))
  require(stopped_ratio > MINIMUM_POLARITY_RATIO and moving_ratio > MINIMUM_POLARITY_RATIO,
          "StandStill polarity failed; vehicle_moving = !bit47 is wrong")


def main(arguments: Sequence[str] | None = None) -> int:
  raw_paths = tuple(sys.argv[1:] if arguments is None else arguments) or DEFAULT_SEGMENT_PATHS
  try:
    print("Validating segment inputs:")
    segment_paths = validate_segment_paths(raw_paths)
    print("Loading and validating capture:")
    segments = load_segments(segment_paths)
    fingerprint = validate_capture(segments)
    print("Checking CarParams:")
    car_params, car_params_sp, car_interface = check_params(fingerprint)
    print("Replaying CarState:")
    replay_state(car_params, car_params_sp, car_interface, segments)
    print("Checking fresh StandStill polarity:")
    check_standstill_polarity(segments)
  except ReplayValidationError as error:
    print(f"REPLAY VALIDATION FAILED: {error}", file=sys.stderr)
    return 1

  print("\nALL OFFLINE CHECKS PASSED (plumbing only; actuation is on-car).")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
