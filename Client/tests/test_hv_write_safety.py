"""Real Python ramp helpers with fake IO; no calibration imports or hardware."""
import ast
import math
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'common'))
from lvhv_protocol_generated import HV_DAC_MAX


class HVWriteSafetyTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'PowerSupplyServerConnection.py'
        tree = ast.parse(path.read_text())
        namespace = dict(math=math, time=time, MAXDACALLOWED=HV_DAC_MAX)
        classes = ast.Module(body=[node for node in tree.body if isinstance(node, ast.ClassDef)], type_ignores=[])
        exec(compile(classes, str(path), 'exec'), namespace)
        self.power = object.__new__(namespace['PowerSupplyServerConnection'])
        self.power.WriteRead = Mock(return_value=[(0,)])
        self.power._log_dac_value = Mock()

    def test_invalid_dac_values_are_rejected_before_logging_or_sending(self):
        for value in (-1, .5, 15000.25, HV_DAC_MAX + 1, float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                self.assertIsNone(self.power._set_hv_by_dac(0, value))
        self.power.WriteRead.assert_not_called()
        self.power._log_dac_value.assert_not_called()

    def test_zero_and_existing_upper_limit_still_send(self):
        for value in (0, float(HV_DAC_MAX)):
            self.assertEqual(self.power._set_hv_by_dac(11, value), [(0,)])
        self.assertEqual(self.power.WriteRead.call_count, 2)
        self.power.WriteRead.assert_called_with('set_hv_by_dac', 11, float(HV_DAC_MAX))

    def test_failed_dac_ack_aborts_real_stepping_without_retry(self):
        self.power.GetHVLock = Mock(return_value=False)
        self.power.QueryLastHVSetting = Mock(return_value=100)
        self.power.QueryTripStatus = Mock(return_value=0)
        self.power.QueryWireVoltage = Mock(return_value=10)
        self.power.WriteRead.return_value = [(-1,)]
        with patch.object(time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'without retry'):
                self.power._take_dac_steps(0, 50, 3, 0)
        self.power.WriteRead.assert_called_once_with('set_hv_by_dac', 0, 150)
        sleep.assert_not_called()
        self.power.QueryWireVoltage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
