"""HV block failures must never shift physical channel IDs; no hardware IO."""
import ast
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

CLIENT = Path(__file__).resolve().parents[1]


def power_class():
    tree = ast.parse((CLIENT / 'PowerSupplyServerConnection.py').read_text())
    namespace = dict(math=math)
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.ClassDef)],
                            type_ignores=[]), '<power-client>', 'exec'), namespace)
    return namespace['PowerSupplyServerConnection']


class HVCollectionChannelsTest(unittest.TestCase):
    def setUp(self):
        self.power = object.__new__(power_class())
        self.power.WriteRead = Mock()

    def test_error_bank_preserves_positions_for_voltage_and_current(self):
        for command, method in [('get_vhvs', self.power.QueryWireVoltages),
                                ('get_ihvs', self.power.QueryWireCurrents)]:
            for failed in (0, 1):
                with self.subTest(command=command, failed_bank=failed):
                    blocks = [[tuple(range(6))], [tuple(range(6, 12))]]
                    blocks[failed] = [(-4,)]
                    self.power.WriteRead.reset_mock(side_effect=True)
                    self.power.WriteRead.side_effect = blocks
                    values = method()
                    expected = list(range(12))
                    expected[failed * 6:failed * 6 + 6] = [None] * 6
                    self.assertEqual(values, expected)
                    self.assertEqual([c.args for c in self.power.WriteRead.call_args_list],
                                     [(command, 0), (command, 6)])

    def test_malformed_blocks_and_nonfinite_readings(self):
        for reply in ([], None, [[1, 2]], [[0] * 7], [[0] * 6, [-4]], [-4]):
            self.assertEqual(self.power._wire_block_values(reply), [None] * 6)
        self.assertEqual(self.power._wire_block_values([[0, -0.1, float('nan'),
                                                        float('inf'), True, '3']]),
                         [0, -0.1, None, None, None, None])
        self.assertEqual(self.power._wire_block_values([[-4]]), [None] * 6)

    def test_both_valid_banks_and_both_failed_banks(self):
        for method in (self.power.QueryWireVoltages, self.power.QueryWireCurrents):
            self.power.WriteRead.side_effect = [[list(range(6))], [list(range(6, 12))]]
            self.assertEqual(method(), list(range(12)))
            self.power.WriteRead.side_effect = [[[-4]], [[-4]]]
            self.assertEqual(method(), [None] * 12)

    def test_exporter_omits_failed_bank_and_retains_physical_channel_ids(self):
        modules = {}
        for name in ('PowerSupplyServerConnection', 'PiHealthConnection', 'RS485Connection'):
            modules[name] = types.ModuleType(name)
            setattr(modules[name], name, None)
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('hv_test_pusher', CLIENT / 'graphite_pusher.py')
            pusher = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pusher)
        self.power.WriteRead.side_effect = [[[-4]], [[11] * 6], [[-4]], [[2] * 6]]
        lines = pusher.collect_hv_metrics(self.power, 'psu10', 123)
        expected = {f'psu10.channels.ch{ch}.{quantity} {value} 123'
                    for ch in range(6, 12)
                    for quantity, value in [('vhv_v', 11), ('ihv_ua', 2)]}
        self.assertEqual(set(lines), expected)


if __name__ == '__main__':
    unittest.main()
