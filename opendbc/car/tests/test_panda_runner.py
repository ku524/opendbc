#!/usr/bin/env python3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from opendbc.car.panda_runner import PandaRunner
from opendbc.car.structs import CarParams, CarParamsSP


class TestPandaRunnerLifecycle(unittest.TestCase):
  def setUp(self):
    self.runner = PandaRunner()
    self.runner.p = Mock()
    self.runner.CI = Mock()
    self.runner.CI.CP = CarParams()
    self.runner.CI.CP_SP = CarParamsSP()
    self.runner._interface_initialization_attempted = True
    self.lifecycle = Mock()
    self.lifecycle.attach_mock(self.runner.CI.deinit, "deinit")
    self.lifecycle.attach_mock(self.runner.p.set_safety_mode, "set_safety_mode")
    self.lifecycle.attach_mock(self.runner.p.reset, "reset")

  @staticmethod
  def enter_dependencies():
    panda = Mock()
    car_interface = Mock()
    car_interface.CP.carFingerprint = "HYUNDAI SONATA HYBRID 2019"
    car_interface.CP.safetyConfigs = [Mock(safetyModel=CarParams.SafetyModel.hyundai, safetyParam=1026)]
    car_interface.CP_SP = CarParamsSP()
    panda_module = SimpleNamespace(Panda=Mock(return_value=panda))
    return panda, car_interface, panda_module

  def test_exit_deinitializes_before_reset(self):
    self.runner.__exit__(None, None, None)

    self.runner.CI.deinit.assert_called_once()
    deinit_arguments = self.runner.CI.deinit.call_args.args
    self.assertIs(deinit_arguments[0], self.runner.CI.CP)
    self.assertIs(deinit_arguments[1], self.runner.CI.CP_SP)
    self.assertIs(deinit_arguments[2].__self__, self.runner)
    self.assertIs(deinit_arguments[3], self.runner.p.can_send_many)
    self.assertEqual([lifecycle_call[0] for lifecycle_call in self.lifecycle.mock_calls],
                     ["set_safety_mode", "deinit", "set_safety_mode", "reset"])
    self.assertEqual(self.runner.p.set_safety_mode.call_args_list,
                     [call(CarParams.SafetyModel.elm327, 1), call(CarParams.SafetyModel.noOutput)])

  def test_exit_resets_panda_when_deinit_raises(self):
    self.runner.CI.deinit.side_effect = RuntimeError("cleanup failed")

    with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
      self.runner.__exit__(None, None, None)

    self.assertEqual(self.runner.p.set_safety_mode.call_args_list,
                     [call(CarParams.SafetyModel.elm327, 1), call(CarParams.SafetyModel.noOutput)])
    self.runner.p.reset.assert_called_once_with()

  def test_enter_failure_after_init_runs_cleanup(self):
    panda, car_interface, panda_module = self.enter_dependencies()

    def fail_final_safety_mode(safety_model, safety_param=None):
      if safety_model == CarParams.SafetyModel.hyundai:
        raise RuntimeError("final safety mode failed")

    panda.set_safety_mode.side_effect = fail_final_safety_mode
    with patch.dict(sys.modules, {"panda": panda_module}), \
         patch("opendbc.car.panda_runner.get_car", return_value=car_interface):
      with self.assertRaisesRegex(RuntimeError, "final safety mode failed"):
        PandaRunner().__enter__()

    car_interface.init.assert_called_once()
    car_interface.deinit.assert_called_once()
    self.assertEqual(panda.reset.call_count, 2)
    self.assertEqual(panda.set_safety_mode.call_args_list[-2:],
                     [call(CarParams.SafetyModel.elm327, 1), call(CarParams.SafetyModel.noOutput)])

  def test_enter_init_failure_runs_cleanup(self):
    panda, car_interface, panda_module = self.enter_dependencies()
    car_interface.init.side_effect = RuntimeError("interface init failed after partial work")

    with patch.dict(sys.modules, {"panda": panda_module}), \
         patch("opendbc.car.panda_runner.get_car", return_value=car_interface):
      with self.assertRaisesRegex(RuntimeError, "interface init failed after partial work"):
        PandaRunner().__enter__()

    car_interface.init.assert_called_once()
    car_interface.deinit.assert_called_once()
    self.assertEqual(panda.reset.call_count, 2)
    self.assertEqual(panda.set_safety_mode.call_args_list[-2:],
                     [call(CarParams.SafetyModel.elm327, 1), call(CarParams.SafetyModel.noOutput)])

  def test_enter_error_is_not_masked_by_cleanup_failures(self):
    panda, car_interface, panda_module = self.enter_dependencies()
    car_interface.deinit.side_effect = RuntimeError("deinit failed")
    panda.reset.side_effect = [None, RuntimeError("reset failed")]

    def fail_safety_modes(safety_model, safety_param=None):
      if safety_model == CarParams.SafetyModel.hyundai:
        raise RuntimeError("final safety mode failed")
      if safety_model == CarParams.SafetyModel.noOutput:
        raise RuntimeError("noOutput failed")

    panda.set_safety_mode.side_effect = fail_safety_modes
    with patch.dict(sys.modules, {"panda": panda_module}), \
         patch("opendbc.car.panda_runner.get_car", return_value=car_interface):
      with self.assertRaisesRegex(RuntimeError, "final safety mode failed"):
        PandaRunner().__enter__()

    car_interface.deinit.assert_called_once()
    self.assertEqual(panda.reset.call_count, 2)

  def test_enter_failure_before_interface_init_skips_deinit(self):
    panda, car_interface, panda_module = self.enter_dependencies()
    with patch.dict(sys.modules, {"panda": panda_module}), \
         patch("opendbc.car.panda_runner.get_car", side_effect=RuntimeError("fingerprint failed")):
      with self.assertRaisesRegex(RuntimeError, "fingerprint failed"):
        PandaRunner().__enter__()

    car_interface.deinit.assert_not_called()
    self.assertEqual(panda.reset.call_count, 2)
    self.assertEqual(panda.set_safety_mode.call_args_list[-2:],
                     [call(CarParams.SafetyModel.elm327, 1), call(CarParams.SafetyModel.noOutput)])

  def test_exit_no_output_failure_still_resets(self):
    def fail_no_output(safety_model, safety_param=None):
      if safety_model == CarParams.SafetyModel.noOutput:
        raise RuntimeError("noOutput failed")

    self.runner.p.set_safety_mode.side_effect = fail_no_output
    with self.assertRaisesRegex(RuntimeError, "noOutput failed"):
      self.runner.__exit__(None, None, None)

    self.runner.CI.deinit.assert_called_once()
    self.runner.p.reset.assert_called_once_with()

  def test_exit_attempts_every_cleanup_step_and_reports_first_error(self):
    self.runner.CI.deinit.side_effect = RuntimeError("deinit failed")
    self.runner.p.reset.side_effect = RuntimeError("reset failed")

    def fail_safety_modes(safety_model, safety_param=None):
      if safety_model == CarParams.SafetyModel.elm327:
        raise RuntimeError("diagnostic failed")
      if safety_model == CarParams.SafetyModel.noOutput:
        raise RuntimeError("noOutput failed")

    self.runner.p.set_safety_mode.side_effect = fail_safety_modes
    with self.assertRaisesRegex(RuntimeError, "diagnostic failed"):
      self.runner.__exit__(None, None, None)

    self.assertEqual(self.runner.p.set_safety_mode.call_args_list,
                     [call(CarParams.SafetyModel.elm327, 1), call(CarParams.SafetyModel.noOutput)])
    self.runner.CI.deinit.assert_called_once()
    self.runner.p.reset.assert_called_once_with()

  def test_body_exception_is_not_masked_by_cleanup_failures(self):
    self.runner.CI.deinit.side_effect = RuntimeError("deinit failed")

    def fail_no_output(safety_model, safety_param=None):
      if safety_model == CarParams.SafetyModel.noOutput:
        raise RuntimeError("noOutput failed")

    self.runner.p.set_safety_mode.side_effect = fail_no_output
    self.runner.p.reset.side_effect = RuntimeError("reset failed")

    suppress_body_error = self.runner.__exit__(RuntimeError, RuntimeError("body failed"), None)

    self.assertFalse(suppress_body_error)
    self.runner.CI.deinit.assert_called_once()
    self.runner.p.reset.assert_called_once_with()


if __name__ == "__main__":
  unittest.main()
