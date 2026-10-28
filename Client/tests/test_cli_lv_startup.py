"""Real CLI parser/sender with fake connection; importing Client.py starts no UI."""
import ast
from collections import namedtuple
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]


class CLIStartup(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'Client/Client.py').read_text())
        wanted = {'process_command', 'execute_command', 'safe_command_execution', 'send_command'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
        nodes += [n for n in tree.body if isinstance(n, ast.Assign) and
                  any(isinstance(t, ast.Name) and t.id == 'commands' for t in n.targets)]
        codes = {}
        for line in (ROOT / 'commands.h').read_text().splitlines():
            words = line.split('//')[0].split()
            if len(words) >= 3 and words[0] == '#define':
                codes[words[1]] = int(words[2], 0)
        self.codes = codes
        self.socket = Mock()
        self.ns = dict(Command=namedtuple('Command',
            'name type_key cmd_output_str_format in_val_type is_channel_cmd',
            defaults=[None, float, True]), command_map=lambda: codes,
            n_channels={'pico': 12, 'hv': 12, 'lv': 6}, connection=self.socket,
            get_lvhv_connection=Mock(), time=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'Client.py', 'exec'), self.ns)

    def test_all_forms_send_one_staggered_command(self):
        for text in ('powerOn', 'powerOn all', 'powerOn -1', 'powerOn 6'):
            with self.subTest(text=text):
                self.socket.reset_mock()
                self.ns['process_command'](text)
                self.socket.send_request.assert_called_once_with(
                    self.codes['COMMAND_powerOn'], self.codes['TYPE_lv'], 6, 0.)

    def test_explicit_immediate_mode_and_individual_channels(self):
        for channel in (0, 2, 5, 7):
            with self.subTest(channel=channel):
                self.socket.reset_mock()
                self.ns['process_command'](f'powerOn {channel}')
                self.socket.send_request.assert_called_once_with(
                    self.codes['COMMAND_powerOn'], self.codes['TYPE_lv'], channel, 0.)

    def test_off_all_keeps_channel6_and_off7_sends_nothing(self):
        self.ns['process_command']('powerOff all')
        self.socket.send_request.assert_called_once_with(
            self.codes['COMMAND_powerOff'], self.codes['TYPE_lv'], 6, 0.)
        self.socket.reset_mock()
        self.ns['process_command']('powerOff 7')
        self.socket.send_request.assert_not_called()
        self.ns['process_command']('powerOn 8')
        self.socket.send_request.assert_not_called()
