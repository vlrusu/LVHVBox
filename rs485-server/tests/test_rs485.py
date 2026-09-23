"""Hardware-free tests for the actual Pi client and GPIO/UART lifecycle."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
import rs485 as com
import com_v2 as cli


class FakeClock:
    now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class Session:
    def __init__(self):
        self.finished = False
        self.next_id = 0x7E7D

    def reserve(self, window):
        self.window = window
        return self.next_id

    def complete(self):
        self.finished = True


class UART:
    def __init__(self, clock, reply, events):
        self.clock, self.reply, self.events = clock, reply, events
        self.buffer = bytearray()
        self.timeout = 0.05
        self.fail_write = False

    def reset_input_buffer(self):
        self.events.append('clear')
        self.buffer.clear()

    def write(self, wire):
        self.events.append('write')
        if self.fail_write:
            raise OSError('injected UART failure')
        self.request = com.Packet.decode(wire)
        self.buffer.extend(self.reply(self.request))
        return len(wire)

    def flush(self):
        self.events.append('flush')

    @property
    def in_waiting(self):
        return min(3, len(self.buffer))  # force fragmented reads across escape pairs

    def read(self, count):
        if not self.buffer:
            self.clock.sleep(self.timeout)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data


def response(request, status=0, raw=0xBEEF, **changes):
    fields = dict(kind=com.RESPONSE, roc=request.roc, transaction=request.transaction,
                  command=request.command, payload=bytes([status]) + raw.to_bytes(2, 'little'))
    fields.update(changes)
    return com.Packet(**fields).encode()


class ClientTests(unittest.TestCase):
    def run_read(self, make_reply, fail_write=False):
        clock, session, events = FakeClock(), Session(), []
        uart = UART(clock, make_reply, events)
        uart.fail_write = fail_write
        bus = com.PiBus(uart, lambda tx: events.append('tx' if tx else 'rx'), session)
        with patch.object(com.time, 'monotonic', clock.monotonic), patch.object(com.time, 'sleep', clock.sleep):
            try:
                result = bus.read_scalar(59, 254)
            except BaseException as exc:
                result = exc
        return result, uart, session, events

    def test_codec_golden(self):
        packet = com.Packet(com.REQUEST, 59, 123, 254)
        self.assertEqual(packet.encode().hex(), '7e02013b007b00fe0074817e')
        reply = bytes.fromhex('7e02023b007b00fe0300efbe61d77e')
        self.assertEqual(com.Packet.decode(reply).scalar_result(packet), 0xBEEF)
        for address in (0, 59, 274, 511):
            for command in range(256):
                p = com.Packet(com.RESPONSE, address, 0x7E7D, command, bytes(range(32)))
                self.assertEqual(com.Packet.decode(p.encode()), p)

    def test_stream_resynchronizes(self):
        packet = com.Packet(com.RESPONSE, 59, 12, 254, b'\0\xef\xbe')
        wire = packet.encode()
        parser = com.FrameStream()
        invalid = b'noise\x7e\x7d\x00\x7e' + b'\x7e' + b'X' * 1000 + b'\x7e'
        invalid += wire[:-4] + b'\x7e'
        result = []
        for byte in invalid + wire:
            result += parser.feed(bytes([byte]))
        self.assertEqual(result, [packet])
        self.assertGreaterEqual(parser.bad_frames, 3)

    def test_corrupt_and_unmatched_are_ignored(self):
        def replies(req):
            corrupt = bytearray(response(req)); corrupt[-3] ^= 1
            return (b'noise' + req.encode() + bytes(corrupt) +
                    response(req, roc=60) + response(req, transaction=1) +
                    response(req, command=31) + response(req, payload=b'\0') +
                    response(req, raw=0x7E7D))
        result, uart, session, events = self.run_read(replies)
        self.assertEqual(result, 0x7E7D)
        self.assertTrue(session.finished)
        self.assertEqual(events, ['rx', 'clear', 'tx', 'write', 'flush', 'rx'])
        self.assertEqual(uart.request.transaction, 0x7E7D)

    def test_status_errors_never_become_measurements(self):
        for status in (1, 2, 3, 4, 5, 255):
            with self.subTest(status=status):
                result, _, session, events = self.run_read(lambda req: response(req, status))
                self.assertIsInstance(result, com.ROCError)
                self.assertIn(f'ROC status {status}', str(result))
                self.assertTrue(session.finished)
                self.assertEqual(events[-1], 'rx')

    def test_timeout_no_retry(self):
        result, _, session, events = self.run_read(lambda req: response(req, transaction=0))
        self.assertIsInstance(result, TimeoutError)
        self.assertFalse(session.finished)
        self.assertEqual(events.count('write'), 1)
        self.assertEqual(events[-1], 'rx')

    def test_write_failure_releases_gpio(self):
        result, _, session, events = self.run_read(lambda req: b'', fail_write=True)
        self.assertIsInstance(result, OSError)
        self.assertFalse(session.finished)
        self.assertEqual(events[-1], 'rx')

    def test_interrupt_releases_gpio(self):
        def interrupt(req):
            raise KeyboardInterrupt()
        result, _, session, events = self.run_read(interrupt)
        self.assertIsInstance(result, KeyboardInterrupt)
        self.assertFalse(session.finished)
        self.assertEqual(events[-1], 'rx')

    def test_persistent_ids_lock_and_restart_holdoff(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            with patch.object(com.time, 'time', return_value=100), patch.object(com.time, 'sleep') as sleep:
                with com.BusSession(state) as session:
                    first = session.reserve(7.1)
                    with self.assertRaisesRegex(RuntimeError, 'another RS485 process'):
                        with com.BusSession(state):
                            pass
                with com.BusSession(state) as session:
                    sleep.assert_called_once()
                    self.assertAlmostEqual(sleep.call_args.args[0], 7.1)
                    self.assertEqual(session.reserve(7.1), (first + 1) & 65535)
                    session.complete()
                self.assertEqual(json.loads(state.read_text())['not_before'], 0)
                state.write_text('{"next_id":65535,"not_before":0}')
                with com.BusSession(state) as session:
                    self.assertEqual(session.reserve(1), 65535)
                    self.assertEqual(session.reserve(1), 0)

    def test_conversion_matches_existing_rules(self):
        rules = json.loads((SERVER / 'transformations.json').read_text())
        self.assertIn('0x0000beef', com.format_value('DBG', 0xBEEF, rules['DBG'], {}, 'MN059'))
        self.assertIn('26.6625', com.format_value('ROC_TEMP', 4797, rules['ROC_TEMP'], {}, 'MN059'))
        self.assertIn('21.0000', com.format_value('Flow', 10, rules['Flow'], {('A0','MN059'):(2,1)}, 'MN059'))

    def test_ilp_signed_conversions_and_word_order(self):
        rules = json.loads((SERVER / 'transformations.json').read_text())
        bus = Mock()
        bus.read_scalar.side_effect = [0x9400, 0x1F17]
        raw = com.read_rule(bus, 59, rules['ILP_PRESSURE'])
        self.assertEqual(raw, 0x1F179400)
        self.assertEqual([call.args for call in bus.read_scalar.call_args_list], [(59, 41), (59, 42)])
        self.assertIn('994.9473', com.format_value('ILP_PRESSURE', raw, rules['ILP_PRESSURE'], {}, 'MN059'))
        for name, raw, expected in [('ILP_TEMP', 0x08CF, '22.5500'),
                                    ('ILP_TEMP', 0xFF9C, '-1.0000'),
                                    ('ILP_PRESSURE', 0xFFF80000, '-1.0000')]:
            self.assertIn(expected, com.format_value(name, raw, rules[name], {}, 'MN059'))
        bus.read_scalar.side_effect = [0x08CF]
        self.assertEqual(com.read_rule(bus, 59, rules['ILP_TEMP']), 0x08CF)

    def test_pressure_requires_both_successful_words(self):
        rule = {'cmdids': [41, 42]}
        for error in (com.ROCError('sensor error'), TimeoutError('no reply')):
            for results, expected_calls in (([error], 1), ([0x9400, error], 2)):
                bus = Mock()
                bus.read_scalar.side_effect = results
                with self.assertRaises(type(error)):
                    com.read_rule(bus, 59, rule)
                self.assertEqual(bus.read_scalar.call_count, expected_calls)

    def test_rule_validation(self):
        for rule in ({'cmdids': []}, {'cmdids': [41]}, {'cmdids': [41,42,43]},
                     {'cmdid':40, 'cmdids':[41,42]}, {'cmdid':256}, {'cmdid':True},
                     {'cmdids':[41,'42']}):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                com.command_ids(rule)

    def test_pressure_dry_run(self):
        with patch.dict(sys.modules, {'serial': None, 'gpiod': None}):
            with patch('builtins.print') as output:
                self.assertEqual(cli.main(['--dry-run', '--name', 'ILP_PRESSURE', '59']), 0)
                self.assertEqual(output.call_count, 2)
                self.assertIn('cmd=41', output.call_args_list[0].args[0])
                self.assertIn('cmd=42', output.call_args_list[1].args[0])

    def test_dry_run_never_imports_hardware(self):
        with patch.dict(sys.modules, {'serial': None, 'gpiod': None}):
            with patch('builtins.print') as output:
                self.assertEqual(cli.main(['--dry-run', '--name', 'DBG', '59']), 0)
                self.assertIn('cmd=254', output.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
