#!/usr/bin/env python3
import unittest
from unittest.mock import Mock, call

from opendbc.car.panda_runner import PandaRunner
from opendbc.car.structs import CarParams, CarParamsSP


class TestPandaRunnerLifecycle(unittest.TestCase):
  def setUp(self):
    self.runner = PandaRunner()
    self.runner.p = Mock()
    self.runner.CI = Mock()
    self.runner.CI.CP = CarParams()
    self.runner.CI.CP_SP = CarParamsSP()
    self.lifecycle = Mock()
    self.lifecycle.attach_mock(self.runner.CI.deinit, "deinit")
    self.lifecycle.attach_mock(self.runner.p.set_safety_mode, "set_safety_mode")
    self.lifecycle.attach_mock(self.runner.p.reset, "reset")

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


if __name__ == "__main__":
  unittest.main()
