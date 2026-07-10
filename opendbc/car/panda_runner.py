from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from opendbc.car.car_helpers import get_car
from opendbc.car.can_definitions import CanData
from opendbc.car.carlog import carlog
from opendbc.car.structs import CarParams, CarControl

if TYPE_CHECKING:
  from panda import Panda


class PandaRunner(AbstractContextManager):
  def __enter__(self):
    from panda import Panda

    self.p = Panda()
    self._interface_initialization_attempted = False
    try:
      self.p.reset()

      # setup + fingerprinting
      self.p.set_safety_mode(CarParams.SafetyModel.elm327, 1)
      self.CI = get_car(self._can_recv, self.p.can_send_many, self.p.set_obd, True, False)
      assert self.CI.CP.carFingerprint.lower() != "mock", "Unable to identify car. Check connections and ensure car is supported."

      safety_model = self.CI.CP.safetyConfigs[0].safetyModel
      self.p.set_safety_mode(CarParams.SafetyModel.elm327, 1)
      self._interface_initialization_attempted = True
      self.CI.init(self.CI.CP, self.CI.CP_SP, self._can_recv, self.p.can_send_many)
      self.p.set_safety_mode(safety_model, self.CI.CP.safetyConfigs[0].safetyParam)
    except BaseException:
      self._cleanup(suppress_errors=True)
      raise

    return self

  def __exit__(self, exc_type, exc_value, traceback):
    self._cleanup(suppress_errors=exc_type is not None)
    return super().__exit__(exc_type, exc_value, traceback)

  def _cleanup(self, suppress_errors: bool) -> None:
    cleanup_errors: list[BaseException] = []

    def run_step(step_name: str, operation: Callable[[], object]) -> None:
      try:
        operation()
      except BaseException as cleanup_error:
        carlog.exception(f"PandaRunner cleanup step failed: {step_name}")
        cleanup_errors.append(cleanup_error)

    run_step("diagnostic safety mode", lambda: self.p.set_safety_mode(CarParams.SafetyModel.elm327, 1))
    if self._interface_initialization_attempted:
      run_step("car interface deinit", lambda: self.CI.deinit(self.CI.CP, self.CI.CP_SP, self._can_recv, self.p.can_send_many))
    run_step("no-output safety mode", lambda: self.p.set_safety_mode(CarParams.SafetyModel.noOutput))
    run_step("panda reset", self.p.reset)

    if cleanup_errors and not suppress_errors:
      raise cleanup_errors[0]

  @property
  def panda(self) -> Panda:
    return self.p

  def _can_recv(self, wait_for_one: bool = False) -> list[list[CanData]]:
    recv = self.p.can_recv()
    while len(recv) == 0 and wait_for_one:
      recv = self.p.can_recv()
    return [[CanData(addr, dat, bus) for addr, dat, bus in recv], ]

  def read(self, strict: bool = True):
    cs = self.CI.update([int(time.monotonic()*1e9), self._can_recv()[0]])
    if strict:
      assert cs.canValid, "CAN went invalid, check connections"
    return cs

  def write(self, cc: CarControl) -> None:
    if cc.enabled and not self.p.health()['controls_allowed']:
      # prevent the car from faulting. print a warning?
      cc = CarControl(enabled=False)
    _, can_sends = self.CI.apply(cc)
    self.p.can_send_many(can_sends, timeout=25)
    self.p.send_heartbeat()


if __name__ == "__main__":
  with PandaRunner() as p:
    print(p.read())
