"""Run with: python3 -m unittest discover -s Client/tests -v"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

# No installed hardware client packages or running PSU are needed for these tests.
modules = {}
for name in ('PowerSupplyServerConnection', 'PiHealthConnection', 'RS485Connection'):
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


class FakeRS485:
    instances = []
    values = {'ROC_TEMP': 26.85, 'ROC_RAIL_1V': 1000.0, 'ROC_RAIL_1.8V': 1800.0,
              'ROC_RAIL_2.5V': 2500.0, 'Flow': 1.234, 'V5KEY': 5.01, 'V2.5KEY': 2.49, 'DCDCTEMP': 32.5}

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.instances.append(self)

    def get_panels(self):
        self.calls.append(('inventory',))
        return {'scanned': True, 'addresses': [253, 101]}

    def direct_read(self, address, name):
        self.calls.append(('direct', address, name))
        return {'value': self.values[name]}

    def read(self, address, name):
        self.calls.append(('cpu', address, name))
        return {'value': self.values[name]}


class GraphiteSchedulesTest(unittest.TestCase):
    def setUp(self):
        FakePower.instances = []
        FakeRS485.instances = []
        pusher.stop_event = threading.Event()
        self.args = pusher.parse_args(['--dry-run'])
        self.patches = [patch.object(pusher, 'PowerSupplyServerConnection', FakePower),
                        patch.object(pusher, 'PiHealthConnection', FakeHealth),
                        patch.object(pusher, 'RS485Connection', FakeRS485)]
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
        self.assertEqual(sorted(map(len, batches)), [21, 25, 30])
        self.assertEqual(len(FakePower.instances), 3)
        self.assertTrue(all(psu.closed for psu in FakePower.instances))
        paths = [line.split()[0] for lines in batches for line in lines]
        self.assertTrue(any(path.endswith('.collector.hv.success') for path in paths))
        self.assertTrue(any(path.endswith('.collector.success') for path in paths))
        self.assertTrue(any(path.endswith('.collector.rs485.success') for path in paths))
        self.assertEqual(len(FakeRS485.instances), 1)

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

    def test_rs485_uses_cached_inventory_direct_tvs_and_calibrated_flow(self):
        conn = FakeRS485()
        with patch.object(pusher.time, 'time', return_value=123):
            lines, success = pusher.collect_rs485_metrics(conn, 'test.psu', lambda **kw: True)
        self.assertTrue(success)
        expected = [('inventory',)]
        for address in (253,101):
            expected += [('direct', address, name) for name in pusher.RS485_DIRECT_PARAMETERS]
            expected += [('cpu', address, name) for name in pusher.RS485_CPU_PARAMETERS]
        self.assertEqual(conn.calls, expected)
        self.assertIn('test.psu.panels.MN253.ROC_TEMP 26.85 123',lines)
        self.assertIn('test.psu.panels.MN253.ROC_RAIL_1_8V 1800.0 123',lines)
        self.assertIn('test.psu.panels.MN101.ROC_RAIL_2_5V 2500.0 123',lines)
        self.assertIn('test.psu.panels.MN253.Flow 1.234 123',lines)
        self.assertIn('test.psu.collector.rs485.panels 2 123',lines)

    def test_flow_failure_preserves_fpga_values_and_continues_other_panels(self):
        conn = FakeRS485()
        def flow(address, name):
            if address==253 and name=='Flow':
                raise RuntimeError('ROC CPU timed out')
            return {'value':1.234}
        with patch.object(conn,'read',side_effect=flow) as read, \
             patch.object(pusher.time,'time',return_value=123), \
             contextlib.redirect_stdout(io.StringIO()):
            lines, success = pusher.collect_rs485_metrics(conn,'test.psu',lambda **kw: True)
        self.assertFalse(success)
        self.assertEqual(read.call_count,8)  # no retry; four CPU parameters per panel
        self.assertFalse(any('.MN253.Flow ' in line for line in lines))
        self.assertIn('test.psu.panels.MN253.ROC_TEMP 26.85 123',lines)
        self.assertIn('test.psu.panels.MN253.collector.success 0 123',lines)
        self.assertIn('test.psu.panels.MN101.collector.success 1 123',lines)

    def test_bad_or_failed_read_omitted_without_cpu_fallback(self):
        for value in (None, float('nan'), float('inf'), True, '123'):
            conn = FakeRS485()
            with patch.object(conn,'direct_read',return_value={'value':value}), \
                 patch.object(conn,'read',wraps=conn.read) as cpu, \
                 contextlib.redirect_stdout(io.StringIO()):
                lines, success = pusher.collect_rs485_metrics(conn,'test.psu',lambda **kw: True)
            self.assertFalse(success)
            self.assertFalse(any('.ROC_' in line for line in lines))
            self.assertEqual([c.args for c in cpu.call_args_list],[(address,name) for address in (253,101) for name in pusher.RS485_CPU_PARAMETERS])
            self.assertTrue(any('.MN253.Flow ' in line for line in lines))

    def test_key_metrics_use_cpu_reads_and_existing_server_conversions(self):
        conn = FakeRS485()
        with patch.object(pusher.time, 'time', return_value=123):
            lines, success = pusher.collect_rs485_metrics(conn, 'test.psu', lambda **kw: True)
        self.assertTrue(success)
        for name,value in [('V5KEY',5.01),('V2.5KEY',2.49),('DCDCTEMP',32.5)]:
            self.assertIn(f'test.psu.panels.MN253.{pusher.sanitize_metric_component(name)} {value} 123',lines)
            self.assertIn(('cpu',253,name),conn.calls)
            self.assertNotIn(('direct',253,name),conn.calls)
        def read(address,name):
            if address==253 and name=='V5KEY':
                raise RuntimeError('failed key read')
            return {'value':conn.values[name]}
        with patch.object(conn,'read',side_effect=read), contextlib.redirect_stdout(io.StringIO()):
            lines,success = pusher.collect_rs485_metrics(conn,'test.psu',lambda **kw: True)
        self.assertFalse(success)
        self.assertFalse(any('.MN253.V5KEY ' in line for line in lines))
        self.assertTrue(any('.MN253.V2_5KEY ' in line for line in lines))
        self.assertTrue(any('.MN101.V5KEY ' in line for line in lines))

    def test_inventory_validation_and_empty_inventory_send_no_panel_requests(self):
        for inventory in ({'scanned':False}, {'scanned':True,'addresses':[253,253]},
                          {'scanned':True,'addresses':['MN253']},
                          {'scanned':True,'addresses':[True]},
                          {'scanned':True,'addresses':[512]}):
            conn = FakeRS485()
            with patch.object(conn,'get_panels',return_value=inventory), self.assertRaises(ValueError):
                pusher.collect_rs485_metrics(conn,'test.psu',lambda **kw: True)
            self.assertEqual(conn.calls,[])
        conn = FakeRS485()
        with patch.object(conn,'get_panels',return_value={'scanned':True,'addresses':[]}):
            lines, success = pusher.collect_rs485_metrics(conn,'test.psu',lambda **kw: True)
        self.assertFalse(success)
        self.assertEqual(conn.calls,[])
        self.assertEqual(len(lines),1)  # only discovered count; no fabricated sensor points

    def test_unavailable_rs485_worker_closes_its_own_power_connection(self):
        self.args.once=True
        batches=[]
        with patch.object(FakeRS485,'get_panels',side_effect=RuntimeError('HTTP unavailable')), \
             patch.object(pusher,'publish_metrics',side_effect=lambda args,lines:batches.append(lines)), \
             contextlib.redirect_stdout(io.StringIO()):
            pusher.collection_worker(self.args,'test.psu','rs485')
        self.assertEqual(len(batches),1)
        self.assertIn('.collector.rs485.success 0 ',batches[0][0])
        self.assertEqual(len(FakePower.instances), 1)
        self.assertTrue(FakePower.instances[0].closed)

    def test_hv_and_slow_continue_while_rs485_is_blocked(self):
        self.args.hv_interval=self.args.interval=0.01
        entered,release,enough=threading.Event(),threading.Event(),threading.Event()
        counts={'hv':0,'slow':0}
        def blocked(*args):
            entered.set()
            release.wait(2)
            return [],False
        def publish(args,lines):
            for name,suffix in [('hv','.collector.hv.success 1 '),('slow','.collector.success 1 ')]:
                if any(suffix in line for line in lines): counts[name]+=1
            if min(counts.values())>=3: enough.set()
        with patch.object(pusher,'collect_rs485_metrics',side_effect=blocked), \
             patch.object(pusher,'publish_metrics',side_effect=publish):
            threads=[threading.Thread(target=pusher.collection_worker,args=(self.args,'test.psu',group))
                     for group in ('rs485','hv','slow')]
            for thread in threads: thread.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(enough.wait(2),'RS485 stalled the LV/HV workers')
            finally:
                pusher.stop_event.set(); release.set()
                for thread in threads: thread.join(2)
            self.assertFalse(any(thread.is_alive() for thread in threads))

    def test_rs485_worker_identifies_as_graphite_for_fair_queue(self):
        self.args.once = True
        with patch.object(pusher, 'RS485Connection', wraps=FakeRS485) as connection, \
             patch.object(pusher, 'collect_rs485_metrics', return_value=([], True)), \
             patch.object(pusher, 'publish_metrics'):
            pusher.collection_worker(self.args, 'test.psu', 'rs485')
        self.assertEqual(connection.call_args.kwargs['client_id'], 'graphite')
        self.assertEqual(connection.call_args.kwargs['timeout'], 30)

    def test_off_worker_emits_disabled_without_inventory_or_panel_reads(self):
        self.args.once = True
        batches = []
        with patch.object(FakePower, 'QuerySwitchingVoltages', create=True,
                          return_value=[0, 1.999, -0.12, 0.8, 1.1, 0]), \
             patch.object(pusher, 'publish_metrics', side_effect=lambda a, lines: batches.append(lines)), \
             contextlib.redirect_stdout(io.StringIO()):
            pusher.collection_worker(self.args, 'test.psu', 'rs485')
        self.assertEqual(FakeRS485.instances[0].calls, [])
        self.assertEqual(len(batches[0]), 1)
        self.assertIn('.collector.rs485.enabled 0 ', batches[0][0])

    def test_any_single_v6_at_two_enables_whole_inventory(self):
        for channel in range(6):
            psu, conn = FakePower(), FakeRS485()
            values = [0] * 6
            values[channel] = 2.0
            with patch.object(psu, 'QuerySwitchingVoltages', return_value=values), \
                 contextlib.redirect_stdout(io.StringIO()):
                lines, success = pusher.collect_rs485_metrics(conn, 'test', pusher.RS485PowerGate(psu))
            self.assertTrue(success)
            self.assertEqual(len(conn.calls), 17)

    def test_invalid_power_never_sends_rs485_requests(self):
        for values in ([0]*5, [0]*5+[-1], [0]*5+[float('nan')], [True]*6, None):
            psu, conn = FakePower(), FakeRS485()
            with patch.object(psu, 'QuerySwitchingVoltages', return_value=values), \
                 self.assertRaises(ValueError):
                pusher.collect_rs485_metrics(conn, 'test', pusher.RS485PowerGate(psu))
            self.assertEqual(conn.calls, [])

    def test_off_mid_scan_stops_remaining_reads_and_preserves_good_sample(self):
        psu, conn = FakePower(), FakeRS485()
        now = [0.0]
        original = conn.direct_read
        def read(address, name):
            result = original(address, name)
            now[0] += 6
            return result
        with patch.object(psu, 'QuerySwitchingVoltages', side_effect=[[6]*6, [0]*6]), \
             patch.object(conn, 'direct_read', side_effect=read), \
             patch.object(pusher.time, 'monotonic', side_effect=lambda: now[0]), \
             contextlib.redirect_stdout(io.StringIO()):
            lines, success = pusher.collect_rs485_metrics(conn, 'test', pusher.RS485PowerGate(psu))
        self.assertIsNone(success)
        self.assertEqual(conn.calls, [('inventory',), ('direct',253,'ROC_TEMP')])
        self.assertTrue(any('.ROC_TEMP ' in line for line in lines))

    def test_off_logs_only_transition_and_power_on_resumes(self):
        psu, conn = FakePower(), FakeRS485()
        gate = pusher.RS485PowerGate(psu)
        output = io.StringIO()
        with patch.object(psu, 'QuerySwitchingVoltages', return_value=[0]*6), \
             contextlib.redirect_stdout(output):
            for _ in range(3):
                self.assertEqual(pusher.collect_rs485_metrics(conn, 'test', gate), ([], None))
        self.assertEqual(output.getvalue().count('OFF:'), 1)
        with patch.object(psu, 'QuerySwitchingVoltages', return_value=[0,0,0,0,0,6]), \
             contextlib.redirect_stdout(output):
            self.assertTrue(pusher.collect_rs485_metrics(conn, 'test', gate)[1])
        self.assertEqual(output.getvalue().count('ON:'), 1)

    def test_defaults_and_invalid_intervals(self):
        self.assertEqual(self.args.hv_interval, 1)
        self.assertEqual(self.args.interval, 20)
        self.assertEqual(self.args.rs485_interval, 20)
        self.assertEqual(self.args.rs485_timeout, 30)
        for option in ('--interval', '--hv-interval', '--timeout', '--rs485-interval', '--rs485-timeout'):
            for value in ('0', '-1', 'nan', 'inf'):
                with self.subTest(option=option, value=value), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        pusher.parse_args([option, value])



class PostgresOutputTest(unittest.TestCase):
    def setUp(self):
        self.args = pusher.parse_args(['--postgres', '--metric-node', 'psu1'])
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.connect = MagicMock(return_value=self.connection)
        self.writer = pusher.PostgresWriter(self.args, self.connect)
        self.addCleanup(setattr, pusher, 'postgres_writer', None)

    def test_metadata_units_and_utc_sample_time(self):
        name, psu, channel, unit, timestamp, value = pusher.postgres_sample(
            'mu2etrk.lvhv.psu1.channels.ch11.ihv_ua 1.25 123', 'mu2etrk.lvhv', 'psu1')
        self.assertEqual((psu, channel, unit, value), ('psu1', 11, 'uA', 1.25))
        self.assertEqual(timestamp.timestamp(), 123)
        self.assertIsNotNone(timestamp.tzinfo)
        for line in ('other.psu1.channels.ch0.vhv_v 1 123',
                     'mu2etrk.lvhv.psu1.panels.MN253.Flow 1.2 124',
                     'mu2etrk.lvhv.psu1.channels.ch0.vhv_v nan 123'):
            with self.assertRaises(ValueError):
                pusher.postgres_sample(line, 'mu2etrk.lvhv', 'psu1')

    def test_only_hv_samples_enter_database_queue(self):
        lines = ['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 1500 123',
                 'mu2etrk.lvhv.psu1.channels.ch0.ihv_ua 0.1 123',
                 'mu2etrk.lvhv.psu1.channels.ch0.v6_v 6 123',
                 'mu2etrk.lvhv.psu1.pcb_temp_c 25 123',
                 'mu2etrk.lvhv.psu1.panels.MN253.ROC_TEMP 26 123',
                 'mu2etrk.lvhv.psu1.collector.hv.success 1 123']
        self.writer.submit(lines)
        self.assertEqual(self.writer.pending.get_nowait(), tuple(lines[:2]))
        self.writer.submit(lines[2:])
        self.assertTrue(self.writer.pending.empty())

    def test_existing_metadata_reused_and_values_parameterized(self):
        self.cursor.fetchall.return_value = [(42,)]
        line = 'mu2etrk.lvhv.psu1.channels.ch0.vhv_v 6.2 123'
        self.writer.write_batch([line])
        self.cursor.execute.assert_called_once_with(
            'SELECT id FROM trk_channel WHERE name = %s AND psu = %s AND channel = %s',
            ('mu2etrk.lvhv.psu1.channels.ch0.vhv_v', 'psu1', 0))
        values = self.cursor.executemany.call_args.args[1]
        self.assertEqual(values[0][1:], (42, 6.2))
        self.assertEqual(values[0][0].timestamp(), 123)
        self.writer.write_batch([line])
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.assertEqual(self.connect.call_count, 1)

    def test_missing_or_ambiguous_metadata_rolls_back_batch(self):
        for rows in ([], [(1,), (2,)]):
            self.cursor.fetchall.return_value = rows
            with self.assertRaises(ValueError):
                self.writer.write_batch(['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 25 123'])
            self.assertFalse(self.writer.channel_ids)
        self.cursor.executemany.assert_not_called()
        self.assertIs(self.connection.__exit__.call_args.args[0], ValueError)

    def test_registration_cache_updated_only_after_commit(self):
        self.args.postgres_register_channels = True
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = (87,)
        self.cursor.executemany.side_effect = RuntimeError('insert failed')
        line = 'mu2etrk.lvhv.psu1.channels.ch0.vhv_v 6 123'
        with self.assertRaises(RuntimeError):
            self.writer.write_batch([line])
        self.assertFalse(self.writer.channel_ids)
        self.cursor.executemany.side_effect = None
        self.writer.write_batch([line])
        self.assertEqual(self.writer.channel_ids[line.split()[0]], 87)
        self.assertIn(unittest.mock.call('SELECT pg_advisory_xact_lock(73482901)'),
                      self.cursor.execute.call_args_list)
        self.assertIn(unittest.mock.call(
            'INSERT INTO trk_channel (name, psu, channel, unit) VALUES (%s, %s, %s, %s) RETURNING id',
            (line.split()[0], 'psu1', 0, 'V')), self.cursor.execute.call_args_list)

    def test_graphite_failure_still_queues_postgres_without_false_sensor_failure(self):
        pusher.postgres_writer = self.writer
        with patch.object(pusher, 'send_graphite', side_effect=OSError('unavailable')), \
             contextlib.redirect_stdout(io.StringIO()):
            pusher.publish_metrics(self.args, ['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 1 123'])
        self.assertEqual(self.writer.pending.get_nowait(), ('mu2etrk.lvhv.psu1.channels.ch0.vhv_v 1 123',))

    def test_dry_run_sends_neither_sink_and_queue_is_bounded(self):
        pusher.postgres_writer = self.writer
        self.args.dry_run = True
        with patch.object(pusher, 'send_graphite') as send, \
             contextlib.redirect_stdout(io.StringIO()):
            pusher.publish_metrics(self.args, ['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 1 123'])
        send.assert_not_called()
        self.assertTrue(self.writer.pending.empty())
        self.args.postgres_queue_size = 1
        writer = pusher.PostgresWriter(self.args, self.connect)
        writer.submit(['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 1 123'])
        with contextlib.redirect_stdout(io.StringIO()):
            writer.submit(['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 2 124'])
        self.assertEqual(writer.pending.qsize(), 1)
        self.assertEqual(writer.pending.get_nowait(), ('mu2etrk.lvhv.psu1.channels.ch0.vhv_v 1 123',))

    def test_hv_filter_preserves_graphite_status_lv_health_and_rs485(self):
        self.args.no_graphite_hv = True
        pusher.postgres_writer = self.writer
        prefix = 'mu2etrk.lvhv.psu1'
        hv = [f'{prefix}.channels.ch0.vhv_v 1 123', f'{prefix}.channels.ch0.ihv_ua 2 123']
        other = [f'{prefix}.{leaf} 1 123' for leaf in
                 ('collector.hv.success', 'channels.ch0.v48_v', 'health.battery_voltage_v', 'panels.mn101.Flow')]
        with patch.object(pusher, 'send_graphite') as send:
            pusher.publish_metrics(self.args, hv + other)
        send.assert_called_once_with(other, self.args.graphite_host, self.args.graphite_port, self.args.timeout)
        self.assertEqual(self.writer.pending.get_nowait(), tuple(hv))
        with patch.object(pusher, 'send_graphite') as send:
            pusher.publish_metrics(self.args, hv)
        send.assert_not_called()

    def test_disabled_graphite_hv_env_and_postgres_guard(self):
        with patch.dict(pusher.os.environ, {'MU2E_GRAPHITE_HV_ENABLED': '0', 'MU2E_POSTGRES_ENABLED': '1'}):
            args = pusher.parse_args([])
        self.assertTrue(args.no_graphite_hv)
        self.assertTrue(args.postgres)
        with patch.dict(pusher.os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                pusher.parse_args(['--no-graphite-hv'])
            args = pusher.parse_args(['--dry-run', '--no-graphite-hv'])
        self.assertTrue(args.no_graphite_hv)

    def test_database_failure_closes_connection_and_redacts_error(self):
        self.writer.submit(['mu2etrk.lvhv.psu1.channels.ch0.vhv_v 25 123'])
        self.cursor.fetchall.side_effect = RuntimeError('secret-password')
        self.writer.finished.set()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.writer.run()
        self.assertNotIn('secret-password', output.getvalue())
        self.connection.close.assert_called_once()
        self.assertIsNone(self.writer.connection)
        self.assertFalse(self.writer.channel_ids)


if __name__ == '__main__':
    unittest.main()
