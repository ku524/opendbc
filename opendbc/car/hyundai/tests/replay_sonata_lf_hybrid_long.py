#!/usr/bin/env python3
"""Offline replay validation for openpilot-longitudinal plumbing on CAR.HYUNDAI_SONATA_LF_HYBRID.

Reads the owner's three local rlog.zst segments directly, not the comma_car_segments network
dataset. Proves: (1) LogReader decodes the logs, (2) get_params yields openpilotLongitudinalControl
with the hyundai safety model plus LONG|HYBRID_GAS|ALT_STANDSTILL param bits, (3) every CAN frame
flows through CarInterface.update() without raising and CarState signals stay in range, (4)
TCS13.StandStill polarity matches speed as a regression guard for the load-bearing assumption.

Does not prove actuation: the route was recorded on stock ACC, so only RX/plumbing is exercised.

Run:
  uv run --with zstandard python opendbc/car/hyundai/tests/replay_sonata_lf_hybrid_long.py
"""
import sys

from opendbc.can.parser import CANParser
from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.can_definitions import CanData
from opendbc.car.car_helpers import interfaces
from opendbc.car.hyundai.values import CAR, HyundaiSafetyFlags
from opendbc.car.logreader import LogReader

PLATFORM = CAR.HYUNDAI_SONATA_LF_HYBRID
SEGMENTS = sys.argv[1:] or [
  "/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--0--rlog.zst",
  "/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--2--rlog.zst",
  "/Users/mark.yeon/Downloads/9f9b411a57b8ce21_00000001--d6d081f0e7--3--rlog.zst",
]


def load_can(paths):
  events = []
  for segment_path in paths:
    segment_events = [message for message in LogReader(segment_path, only_union_types=True, sort_by_time=True) if message.which() == "can"]
    print(f"  {segment_path}: {len(segment_events)} can events")
    events.extend(segment_events)
  events.sort(key=lambda message: message.logMonoTime)
  return events


def check_params():
  car_interface = interfaces[PLATFORM]
  fingerprint = gen_empty_fingerprint()
  car_params = car_interface.get_params(PLATFORM, fingerprint, [], alpha_long=True, is_release=False, docs=False)
  car_params_sp = car_interface.get_params_sp(car_params, PLATFORM, fingerprint, [], alpha_long=True, is_release_sp=False, docs=False)
  assert car_params.openpilotLongitudinalControl, "openpilotLongitudinalControl is False"
  assert car_params.safetyConfigs[-1].safetyModel == structs.CarParams.SafetyModel.hyundai, "not on hyundai safety"
  safety_param = car_params.safetyConfigs[-1].safetyParam
  for safety_flag in (HyundaiSafetyFlags.LONG, HyundaiSafetyFlags.HYBRID_GAS, HyundaiSafetyFlags.ALT_STANDSTILL):
    assert safety_param & safety_flag.value, f"safetyParam missing {safety_flag.name}"
  print("  CarParams OK: hyundai safety, long ON, param LONG|HYBRID_GAS|ALT_STANDSTILL")
  return car_params, car_params_sp, car_interface


def replay_state(car_params, car_params_sp, car_interface, can_msgs):
  replay_interface = car_interface(car_params, car_params_sp)
  car_control = structs.CarControl().as_reader()
  car_control_sp = structs.CarControlSP()
  max_speed = 0.0
  replayed_frames = 0
  for message in can_msgs:
    frames = [CanData(can.address, can.dat, can.src) for can in message.can]
    car_state, _ = replay_interface.update([(message.logMonoTime, frames)])
    replay_interface.apply(car_control, car_control_sp, message.logMonoTime)
    max_speed = max(max_speed, car_state.vEgo)
    assert -1.0 <= car_state.vEgo <= 80.0, f"vEgo out of range: {car_state.vEgo}"
    replayed_frames += 1
  print(f"  replayed {replayed_frames} frames without error; max vEgo={max_speed * 3.6:.1f} km/h")


def check_standstill_polarity(can_msgs):
  can_parser = CANParser("hyundai_can_generated", [("TCS13", 0), ("WHL_SPD11", 0)], 0)
  stopped_bit1 = stopped_count = moving_bit0 = moving_count = 0
  for message in can_msgs:
    can_parser.update((message.logMonoTime, [(can.address, bytes(can.dat), can.src) for can in message.can]))
    standstill = int(round(can_parser.vl["TCS13"]["StandStill"]))
    wheel_speeds = can_parser.vl["WHL_SPD11"]
    wheel_speed = (wheel_speeds["WHL_SPD_FL"] + wheel_speeds["WHL_SPD_FR"] +
                   wheel_speeds["WHL_SPD_RL"] + wheel_speeds["WHL_SPD_RR"]) / 4.0
    if wheel_speed < 0.3:
      stopped_count += 1
      stopped_bit1 += standstill == 1
    elif wheel_speed > 5.0:
      moving_count += 1
      moving_bit0 += standstill == 0
  stopped_ratio = stopped_bit1 / max(stopped_count, 1)
  moving_ratio = moving_bit0 / max(moving_count, 1)
  print(f"  StandStill polarity: stopped->1 {100 * stopped_ratio:.1f}%, moving->0 {100 * moving_ratio:.1f}%")
  assert stopped_ratio > 0.9 and moving_ratio > 0.9, "StandStill polarity FAILED; vehicle_moving = !bit47 is wrong"


def main():
  print("Loading segments:")
  can_msgs = load_can(SEGMENTS)
  print("Checking CarParams:")
  car_params, car_params_sp, car_interface = check_params()
  print("Replaying CarState:")
  replay_state(car_params, car_params_sp, car_interface, can_msgs)
  print("Checking StandStill polarity (regression guard):")
  check_standstill_polarity(can_msgs)
  print("\nALL OFFLINE CHECKS PASSED (plumbing only; actuation is on-car).")


if __name__ == "__main__":
  main()
