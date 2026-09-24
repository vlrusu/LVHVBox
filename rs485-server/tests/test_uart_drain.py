"""UART drain boundary tests: physical completion, errors and DE ownership."""
import errno
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rs485


class DrainTests(unittest.TestCase):
    def test_waits_for_physical_empty_even_when_software_queue_is_empty(self):
        uart = Mock(out_waiting=0)
        uart.fileno.return_value = 17
        states = iter([0, 0, 1])
        def ioctl(fd, command, state, mutate):
            self.assertEqual((fd, command, mutate), (17, 0x5459, True))
            state[0] = next(states)
        with patch('fcntl.ioctl', side_effect=ioctl), patch.object(rs485.time, 'sleep') as sleep:
            rs485.drain_uart(uart)
        self.assertEqual(sleep.call_count, 2)
        uart.flush.assert_not_called()

    def test_unsupported_driver_drains_and_warns(self):
        uart = Mock()
        with patch('fcntl.ioctl', side_effect=OSError(errno.ENOTTY, 'unsupported')):
            with self.assertWarnsRegex(RuntimeWarning, 'may miss fast FPGA replies'):
                rs485.drain_uart(uart)
        uart.flush.assert_called_once_with()

    def test_io_error_drains_before_raising(self):
        uart = Mock()
        with patch('fcntl.ioctl', side_effect=OSError(errno.EIO, 'failure')):
            with self.assertRaises(OSError):
                rs485.drain_uart(uart)
        uart.flush.assert_called_once_with()

    def test_stuck_transmitter_drains_before_timeout(self):
        uart = Mock()
        with patch('fcntl.ioctl'), patch.object(rs485.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                rs485.drain_uart(uart)
        uart.flush.assert_called_once_with()

    def test_bus_uses_drain_before_releasing_direction_on_error(self):
        uart, session, events = Mock(), Mock(), []
        session.reserve.return_value = 42
        uart.write.side_effect = lambda data: len(data)
        def drain():
            self.assertEqual(events[-1], True)
            events.append('drain')
            raise OSError('injected drain failure')
        bus = rs485.PiBus(uart, events.append, session, drain=drain)
        with self.assertRaises(OSError):
            bus.read_panel_id(269)
        self.assertEqual(events, [False, True, 'drain', False])
        uart.flush.assert_not_called()
        session.complete.assert_not_called()


if __name__ == '__main__':
    unittest.main()
