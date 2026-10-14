"""Exercise the real watchdog loop with simulated time and no hardware/network I/O."""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).resolve().parents[1] / 'network-watch.py'
spec = importlib.util.spec_from_file_location('network_watch_grace_test', path)
watch = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = watch
spec.loader.exec_module(watch)

class GracePeriodTests(unittest.TestCase):
    def run_scan(self, scans, dry_run=False):
        cycle = 0
        sent = []
        endpoints = [watch.ProbeEndpoint('master1', 1), watch.ProbeEndpoint('master2', 2)]
        client = types.SimpleNamespace(power_off=lambda reason: sent.append((scans[cycle][0], reason)))
        def probe(endpoint):
            reachable = scans[cycle][1][endpoints.index(endpoint)]
            return reachable, None if reachable else 'simulated timeout'
        def sleep(_):
            nonlocal cycle
            cycle += 1
            if cycle == len(scans):
                watch.running = False
        with patch.object(watch, 'running', True), patch.object(watch, 'failure_streak', 0), \
             patch.object(watch, 'shutdown_latched', False), patch.object(watch, 'DEFAULT_GRACE_PERIOD_S', 1800), \
             patch.object(watch, 'parse_args', return_value=types.SimpleNamespace(dry_run=dry_run)), \
             patch.object(watch, 'configure_logging'), patch.object(watch, 'logging'), \
             patch.object(watch, 'LocalPowerOffClient', return_value=client), \
             patch.object(watch, 'build_master_endpoints', return_value=endpoints), \
             patch.object(watch, 'probe_endpoint', side_effect=probe), \
             patch.object(watch.time, 'monotonic', side_effect=lambda: scans[cycle][0]), \
             patch.object(watch.time, 'sleep', side_effect=sleep):
            self.assertEqual(watch.main(), 0)
        return sent

    def test_boundary_and_repeated_shutdown_until_recovery(self):
        failed = (True, False)
        sent = self.run_scan([(0, failed), (33, failed), (66, failed),
                              (1799.99, failed), (1800, failed), (1833, failed),
                              (1860, (True, True)), (1861, failed)])
        self.assertEqual([t for t, _ in sent], [1800, 1833])

    def test_recovery_restarts_full_grace_even_if_different_endpoint_later_fails(self):
        sent = self.run_scan([(0, (True, False)), (1799, (True, False)),
                              (1800, (True, True)), (1801, (False, True)),
                              (3599, (False, True)), (3601, (False, True))])
        self.assertEqual([t for t, _ in sent], [3601])

    def test_poll_delay_cannot_trigger_early_shutdown(self):
        sent = self.run_scan([(100, (False, True)), (1000, (False, True)),
                              (1899, (False, True)), (1933, (False, True))])
        self.assertEqual([t for t, _ in sent], [1933])

    def test_dry_run_never_sends_power_command(self):
        self.assertEqual(self.run_scan([(0, (False, False)), (1800, (False, False))], True), [])

    def test_invalid_grace_rejected(self):
        for value in [0, -1, float('inf'), float('nan')]:
            with self.subTest(value=value), patch.object(watch, 'DEFAULT_GRACE_PERIOD_S', value), \
                 patch.object(watch, 'parse_args', return_value=types.SimpleNamespace(dry_run=True)):
                with self.assertRaises(SystemExit):
                    watch.main()

if __name__ == '__main__':
    unittest.main()
