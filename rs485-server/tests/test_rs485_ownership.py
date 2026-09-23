"""Exercise persistent ownership and timeout recovery through the public class."""
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rs485
import com_v2
from test_rs485 import FakeClock, UART, response


class OwnershipTests(unittest.TestCase):
    def test_exclusive_for_lifetime_and_holdoff_after_timeout_without_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'lock.json'
            clock, events = FakeClock(), []
            opened, closed, sent_at = [], [], []
            replies = [False, True]

            def reply(request):
                sent_at.append(clock.now)
                return response(request) if replies.pop(0) else b''

            @contextmanager
            def factory():
                with rs485.BusSession(state) as session:
                    opened.append(True)
                    try:
                        yield rs485.PiBus(UART(clock, reply, events), events.append, session)
                    finally:
                        closed.append(True)

            device = rs485.RS485(bus_factory=factory)
            with patch.object(rs485.time, 'time', lambda: clock.now + 100), \
                    patch.object(rs485.time, 'monotonic', clock.monotonic), \
                    patch.object(rs485.time, 'sleep', clock.sleep):
                with self.assertRaisesRegex(RuntimeError, 'not open'):
                    device.read(253, 'DBG')
                self.assertFalse(opened)
                with device:
                    # Even an idle server owns the bus, before any request.
                    with self.assertRaisesRegex(RuntimeError, 'stop rs485-server'):
                        with rs485.RS485(bus_factory=factory):
                            self.fail('competing owner admitted')
                    with self.assertRaises(TimeoutError):
                        device.read(253, 'DBG')
                    self.assertEqual(device.read(253, 'DBG')['value'], 0xBEEF)
                    self.assertEqual(len(opened), 1)
                    self.assertFalse(closed)
                    # Timeout plus remaining holdoff must precede second TX.
                    self.assertGreaterEqual(sent_at[1] - sent_at[0], 7.099)
                self.assertEqual(len(closed), 1)
                with rs485.RS485(bus_factory=factory):
                    pass  # standalone ownership succeeds after server closes
                self.assertEqual(len(opened), 2)

    def test_cli_uses_shared_class_and_releases_on_failure(self):
        events = []
        @contextmanager
        def factory():
            events.append('open')
            try:
                class Bus:
                    def read_scalar(self, address, command):
                        raise TimeoutError('injected timeout')
                yield Bus()
            finally:
                events.append('closed')
        device = rs485.RS485(bus_factory=factory)
        with patch.object(com_v2, 'RS485', return_value=device), patch('builtins.print'):
            self.assertEqual(com_v2.main(['253', '--name', 'DBG']), 1)
        self.assertEqual(events, ['open', 'closed'])

    def test_bad_cli_name_never_acquires_device(self):
        @contextmanager
        def factory():
            self.fail('invalid CLI request opened UART')
            yield
        device = rs485.RS485(bus_factory=factory)
        with patch.object(com_v2, 'RS485', return_value=device), patch('builtins.print'):
            self.assertEqual(com_v2.main(['253', '--name', 'bad_variable']), 1)


if __name__ == '__main__':
    unittest.main()
