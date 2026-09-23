"""Run with: python3 -m unittest discover -s Client/tests -v"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

# No installed hardware client packages or running PSU are needed for these tests.
modules = {}
for name in ('PowerSupplyServerConnection', 'PiHealthConnection'):
    module = types.ModuleType(name)
    setattr(module, name, None)
    modules[name] = module
with patch.dict(sys.modules, modules):
    spec = importlib.util.spec_from_file_location('graphite_pusher', Path(__file__).parents[1] / 'graphite_pusher.py')
    pusher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pusher)


class FakePower:
    instances = []

    def __init__(self, *args):
        self.closed = False
        self.calls = []
        self.instances.append(self)

    def close(self):
        self.closed = True

    def __getattr__(self, name):
        def query():
            self.calls.append(name)
            if name == 'QueryPcbTemp':
                return 25.0
            count = 12 if name.startswith('QueryWire') else 6
            return list(range(count))
        return query


class FakeHealth:
    def __init__(self, *args, **kwargs):
        pass

    def get_health(self):
        return {'battery_voltage_v': 12.0, 'battery_capacity_pct': 80,
                'battery_error': None,
                'ac_inputs': {'gpio6_ac_status': {'ac_power_present': True}}}


class GraphiteSchedulesTest(unittest.TestCase):
    def setUp(self):
        FakePower.instances = []
        pusher.stop_event = threading.Event()
        self.args = pusher.parse_args(['--dry-run'])
        self.patches = [patch.object(pusher, 'PowerSupplyServerConnection', FakePower),
                        patch.object(pusher, 'PiHealthConnection', FakeHealth)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_metric_groups_preserve_names_and_do_not_overlap(self):
        psu = FakePower()
        hv = pusher.collect_hv_metrics(psu, 'test.psu', 123)
        self.assertEqual(psu.calls, ['QueryWireVoltages', 'QueryWireCurrents'])
        psu.calls.clear()
        slow = pusher.collect_lv_metrics(psu, 'test.psu', 123)
        slow += pusher.collect_health_metrics(FakeHealth(), 'test.psu', 123)
        self.assertEqual(len(hv), 24)
        self.assertEqual(len(slow), 29)
        self.assertNotIn('QueryWireVoltages', psu.calls)
        self.assertNotIn('QueryWireCurrents', psu.calls)
        self.assertFalse({line.split()[0] for line in hv} & {line.split()[0] for line in slow})
        self.assertIn('test.psu.channels.ch11.vhv_v 11 123', hv)
        self.assertIn('test.psu.channels.ch5.v48_v 5 123', slow)

    def test_once_uses_separate_connections_and_no_graphite_send(self):
        batches = []
        with patch.object(sys, 'argv', ['graphite-pusher', '--once', '--dry-run']), \
             patch.object(pusher.signal, 'signal'), \
             patch.object(pusher, 'emit_test_output', side_effect=batches.append), \
             patch.object(pusher, 'send_graphite') as send:
            self.assertEqual(pusher.main(), 0)
        send.assert_not_called()
        self.assertEqual(sorted(map(len, batches)), [25, 30])
        self.assertEqual(len(FakePower.instances), 2)
        self.assertTrue(all(psu.closed for psu in FakePower.instances))
        paths = [line.split()[0] for lines in batches for line in lines]
        self.assertTrue(any(path.endswith('.collector.hv.success') for path in paths))
        self.assertTrue(any(path.endswith('.collector.success') for path in paths))

    def test_hv_continues_while_slow_collection_is_blocked(self):
        self.args.hv_interval = 0.01
        entered = threading.Event()
        release = threading.Event()
        three_hv_cycles = threading.Event()
        hv_batches = []

        def blocked(*args):
            entered.set()
            release.wait(2)
            return []

        def publish(args, lines):
            if any('.collector.hv.success 1 ' in line for line in lines):
                hv_batches.append(lines)
                if len(hv_batches) >= 3:
                    three_hv_cycles.set()

        with patch.object(pusher, 'collect_lv_metrics', side_effect=blocked), \
             patch.object(pusher, 'publish_metrics', side_effect=publish):
            slow = threading.Thread(target=pusher.collection_worker, args=(self.args, 'test.psu', 'slow'))
            hv = threading.Thread(target=pusher.collection_worker, args=(self.args, 'test.psu', 'hv'))
            slow.start()
            hv.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(three_hv_cycles.wait(2), 'HV stalled behind the slow collector')
                self.assertFalse(release.is_set())
            finally:
                pusher.stop_event.set()
                release.set()
                slow.join(2)
                hv.join(2)
            self.assertFalse(slow.is_alive())
            self.assertFalse(hv.is_alive())
        self.assertEqual(len(FakePower.instances), 2)
        self.assertTrue(all(psu.closed for psu in FakePower.instances))

    def test_failed_hv_read_closes_connection_and_retries(self):
        self.args.hv_interval = 0.001
        batches = []

        def publish(args, lines):
            batches.append(lines)
            if len(batches) == 2:
                pusher.stop_event.set()

        with patch.object(pusher, 'collect_hv_metrics', side_effect=[OSError('disconnected'), []]), \
             patch.object(pusher, 'publish_metrics', side_effect=publish), \
             contextlib.redirect_stdout(io.StringIO()):
            pusher.collection_worker(self.args, 'test.psu', 'hv')
        self.assertIn('.collector.hv.success 0 ', batches[0][0])
        self.assertIn('.collector.hv.success 1 ', batches[1][0])
        self.assertEqual(len(FakePower.instances), 2)
        self.assertTrue(all(psu.closed for psu in FakePower.instances))

    def test_overruns_skip_missed_slots_without_catchup_bursts(self):
        now = [0.0]
        starts = []
        waits = []

        class ClockEvent:
            def is_set(self):
                return len(starts) >= 3

            def wait(self, delay):
                waits.append(delay)
                now[0] += delay

        def collect(*args):
            starts.append(now[0])
            now[0] += 2.4
            return []

        with patch.object(pusher, 'stop_event', ClockEvent()), \
             patch.object(pusher.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(pusher, 'collect_hv_metrics', side_effect=collect), \
             patch.object(pusher, 'publish_metrics'):
            pusher.collection_worker(self.args, 'test.psu', 'hv')
        self.assertEqual(starts, [0.0, 3.0, 6.0])
        for delay in waits:
            self.assertAlmostEqual(delay, 0.6)

    def test_defaults_and_invalid_intervals(self):
        self.assertEqual(self.args.hv_interval, 1)
        self.assertEqual(self.args.interval, 20)
        for option in ('--interval', '--hv-interval', '--timeout'):
            for value in ('0', '-1', 'nan', 'inf'):
                with self.subTest(option=option, value=value), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        pusher.parse_args([option, value])


if __name__ == '__main__':
    unittest.main()
