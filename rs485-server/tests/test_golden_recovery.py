"""Explicit user recovery, tested with fake UART/clock and no detector access."""
import contextlib
import io
import unittest
from unittest.mock import patch
from test_rs485 import FakeClock, Session, UART, response, com, cli

class RecoveryTests(unittest.TestCase):
    def run_control(self, reply, activate=True):
        clock, session, events = FakeClock(), Session(), []
        uart = UART(clock, reply, events)
        bus = com.PiBus(uart, lambda tx: events.append('tx' if tx else 'rx'), session)
        with patch.object(com.time, 'monotonic', clock.monotonic), patch.object(com.time, 'sleep', clock.sleep):
            try:
                value = bus.control(253, activate=activate)
            except Exception as exc:
                value = exc
        return value, uart, events, session

    def test_panel_id_uses_special_command_and_checks_identity(self):
        for value in (253, 254):
            clock, session, events = FakeClock(), Session(), []
            uart = UART(clock, lambda r: response(r, kind=com.CONTROL_RESPONSE, raw=value), events)
            bus = com.PiBus(uart, lambda tx: events.append('tx' if tx else 'rx'), session)
            with patch.object(com.time, 'monotonic', clock.monotonic), patch.object(com.time, 'sleep', clock.sleep):
                if value == 253:
                    self.assertEqual(bus.read_panel_id(253), 253)
                else:
                    with self.assertRaisesRegex(com.ROCError, 'does not match'):
                        bus.read_panel_id(253)
            self.assertEqual(uart.request, com.Packet(com.CONTROL_REQUEST,253,0x7E7D,2,b''))
            self.assertEqual(events.count('write'), 1)
        with patch.object(com,'open_bus',side_effect=AssertionError('hardware open')), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['253','--panel-id','--dry-run']),0)
            self.assertIn('PANEL ID:', out.getvalue())

    def test_direct_tvs_wire_status_and_no_cpu_fallback(self):
        for command in range(3, 7):
            for status in (0, 7):
                clock, session, events = FakeClock(), Session(), []
                # A CPU response with the right ID must not satisfy a direct request.
                uart = UART(clock, lambda r: response(r, raw=1) + response(
                    r, kind=com.CONTROL_RESPONSE, raw=0x7E7D, status=status), events)
                bus = com.PiBus(uart, lambda tx: events.append('tx' if tx else 'rx'), session)
                with patch.object(com.time, 'monotonic', clock.monotonic), patch.object(com.time, 'sleep', clock.sleep):
                    if status:
                        with self.assertRaisesRegex(com.ROCError, 'unavailable or stale'):
                            bus.read_direct(253, command)
                    else:
                        self.assertEqual(bus.read_direct(253, command), 0x7E7D)
                self.assertEqual(uart.request, com.Packet(com.CONTROL_REQUEST,253,0x7E7D,command,b''))
                self.assertEqual(events.count('write'), 1)
                self.assertTrue(session.finished)
        for command in (0, 1, 2, 7, True):
            with self.assertRaises(ValueError):
                bus.read_direct(253, command)
        self.assertEqual(events.count('write'), 1)

    def test_direct_tvs_dry_run_is_read_only(self):
        with patch.object(com,'open_bus',side_effect=AssertionError('hardware open')), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['253','--direct','--dry-run']),0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 4)
        for line, command in zip(lines, range(3, 7)):
            packet = com.Packet.decode(bytes.fromhex(line.split('request=')[1]))
            self.assertEqual((packet.kind, packet.command, packet.payload), (3,command,b''))
        with patch.object(com,'open_bus',side_effect=AssertionError('hardware open')), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['253','--direct','DBG','--dry-run']),1)

    def test_explicit_activation_wire_and_matching_ack_only(self):
        def replies(r):
            return (response(r, raw=0) + response(r, kind=com.CONTROL_RESPONSE, transaction=1, raw=0) +
                    response(r, kind=com.CONTROL_RESPONSE, raw=0))
        value, uart, events, session = self.run_control(replies)
        self.assertEqual(value, 0)
        self.assertEqual(uart.request, com.Packet(com.CONTROL_REQUEST,253,0x7E7D,1,b'GOLD'))
        self.assertEqual(events.count('write'),1)
        self.assertEqual(events[-1], 'rx')
        self.assertTrue(session.finished)

    def test_lost_ack_is_unknown_and_never_retried(self):
        value, _, events, session = self.run_control(lambda r: b'')
        self.assertIsInstance(value, TimeoutError)
        self.assertIn('outcome unknown', str(value))
        self.assertEqual(events.count('write'), 1)
        self.assertFalse(session.finished)

    def test_busy_and_wrong_index_ack_are_not_success(self):
        for status, raw in [(6,0),(0,2)]:
            value, _, events, _ = self.run_control(lambda r: response(r,kind=com.CONTROL_RESPONSE,status=status,raw=raw))
            self.assertIsInstance(value, com.ROCError)
            self.assertEqual(events.count('write'),1)

    def test_status_never_sends_activation_token(self):
        value, uart, _, _ = self.run_control(lambda r: response(r,kind=com.CONTROL_RESPONSE,raw=0x120E),False)
        self.assertEqual(value,0x120E)
        self.assertEqual((uart.request.command,uart.request.payload),(0,b''))

    def test_dry_run_opens_no_hardware(self):
        with patch.object(com,'open_bus',side_effect=AssertionError('hardware open')), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['253','--recover-golden','--dry-run']),0)
            self.assertIn('ACTIVATE GOLDEN IMAGE 0',out.getvalue())

if __name__ == '__main__':
    unittest.main()
