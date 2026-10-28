"""Offline tests: no sensor, network, credentials, or database required."""
import importlib.util
import os
from pathlib import Path
import queue
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
    "i2c_sensor_under_test", Path(__file__).parents[1] / "i2c-sensor-server.py")
server = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = server
with patch.dict(sys.modules, {"smbus2": types.SimpleNamespace(SMBus=MagicMock())}):
    spec.loader.exec_module(server)


def reading(**changes):
    values = dict(temperature_c=25.5, pressure_hpa=1001.2, humidity_rh=42.0,
                  dew_point_c=11.3, gas_resistance_ohms=12345.0, heat_stable=True)
    values.update(changes)
    return server.SensorReading("2026-10-27T21:00:00Z", "local display only",
                                "bme680", values, "bme680")


class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = dict(server.state)
        self.addCleanup(server.state.update, self.saved_state)
        server.state.update(hostname="mu2e-trk-psu13", status="ok",
                            postgres_batches_written=0, postgres_batches_dropped=0,
                            postgres_fields_skipped=0, postgres_last_error=None,
                            postgres_last_success_utc=None)
        for key, value in (("DEFAULT_POSTGRES_ENABLED", True),
                           ("DEFAULT_POSTGRES_REGISTER_CHANNELS", True),
                           ("DEFAULT_I2C_BUS", 4), ("DEFAULT_I2C_ADDR", 0x76)):
            item = patch.object(server, key, value)
            item.start()
            self.addCleanup(item.stop)
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.side_effect = [(i,) for i in range(1, 13)]
        self.connect = MagicMock(return_value=self.connection)
        self.writer = server.PostgresWriter(self.connect)

    def test_six_fields_preserve_units_identity_and_utc(self):
        samples = server.postgres_samples(reading())
        self.assertEqual(len(samples), 6)
        name, host, address, unit, quantity, timestamp, value = samples[0]
        self.assertEqual(name, "mu2etrk.environment.mu2e-trk-psu13.channels.i2c4_addr76_bme680.temperature_c")
        self.assertEqual((host, address, unit, quantity, value),
                         ("mu2e-trk-psu13", 118, "C", "temperature_c", 25.5))
        self.assertEqual(timestamp.isoformat(), "2026-10-27T21:00:00+00:00")
        self.assertTrue(all(sample[0].split(".")[5] == sample[4] for sample in samples))
        self.assertEqual([s[3] for s in samples], ["C", "hPa", "%RH", "C", "ohm", "bool"])
        self.assertEqual(samples[-1][-1], 1.0)
        self.assertEqual(server.postgres_samples(reading(heat_stable=False))[-1][-1], 0.0)

    def test_unavailable_dew_point_and_gas_are_omitted(self):
        samples = server.postgres_samples(reading(dew_point_c=None, gas_resistance_ohms=None))
        self.assertEqual(len(samples), 4)
        self.assertNotIn("gas_resistance_ohms", [s[4] for s in samples])

    def test_invalid_numbers_and_wrong_types_never_enter_database(self):
        with self.assertLogs(level="WARNING"):
            samples = server.postgres_samples(reading(temperature_c=float("nan"),
                pressure_hpa=float("inf"), humidity_rh=True, dew_point_c="25", heat_stable=1))
        self.assertEqual([s[4] for s in samples], ["gas_resistance_ohms"])
        self.assertEqual(server.state["postgres_fields_skipped"], 5)

    def test_naive_timestamp_is_rejected_before_queueing(self):
        item = reading()
        item = server.SensorReading("2026-10-27T21:00:00", item.timestamp_local,
                                    item.sensor_type, item.values, item.source)
        with self.assertLogs(level="ERROR"):
            self.writer.submit(item)
        self.assertTrue(self.writer.pending.empty())
        self.assertEqual(server.state["postgres_last_error"], "ValueError")

    def test_registration_and_samples_commit_together_then_cache(self):
        samples = server.postgres_samples(reading())
        self.writer.write_batch(samples)
        self.assertEqual(len(self.writer.channel_ids), 6)
        self.assertEqual(server.state["postgres_batches_written"], 1)
        self.assertEqual(server.state["postgres_last_success_utc"], "2026-10-27T21:00:00+00:00")
        self.cursor.execute.assert_any_call("SELECT pg_advisory_xact_lock(73482901)")
        self.cursor.execute.assert_any_call(
            "INSERT INTO public.trk_channel (name, psu, channel, unit) "
            "VALUES (%s, %s, %s, %s) RETURNING id", samples[0][:4])
        inserted = self.cursor.executemany.call_args.args[1]
        self.assertEqual(inserted[0], (samples[0][5], 1, 25.5))
        self.cursor.execute.reset_mock()
        self.writer.write_batch(samples)
        self.cursor.execute.assert_not_called()
        self.assertEqual(self.connect.call_count, 1)

    def test_reuses_only_matching_existing_metadata(self):
        self.cursor.fetchall.return_value = [(42, "C", "temperature_c")]
        sample = server.postgres_samples(reading())[:1]
        self.writer.write_batch(sample)
        self.cursor.fetchone.assert_not_called()
        self.assertEqual(self.cursor.executemany.call_args.args[1][0][1], 42)

    def test_duplicate_or_wrong_metadata_rolls_back(self):
        for rows in ([(1, "C", "temperature_c"), (2, "C", "temperature_c")],
                     [(1, "V", "temperature_c")], [(1, "C", "vhv_v")]):
            self.cursor.fetchall.return_value = rows
            with self.assertRaises(ValueError):
                self.writer.write_batch(server.postgres_samples(reading())[:1])
            self.assertFalse(self.writer.channel_ids)
        self.cursor.executemany.assert_not_called()
        self.assertIs(self.connection.__exit__.call_args.args[0], ValueError)

    def test_registration_can_be_disabled(self):
        with patch.object(server, "DEFAULT_POSTGRES_REGISTER_CHANNELS", False):
            with self.assertRaises(ValueError):
                self.writer.write_batch(server.postgres_samples(reading()))
        self.cursor.fetchone.assert_not_called()
        self.cursor.executemany.assert_not_called()

    def test_commit_failure_does_not_cache_ids_or_report_success(self):
        self.connection.__exit__.side_effect = RuntimeError("secret connection detail")
        with self.assertRaises(RuntimeError):
            self.writer.write_batch(server.postgres_samples(reading()))
        self.assertFalse(self.writer.channel_ids)
        self.assertEqual(server.state["postgres_batches_written"], 0)
        self.assertIsNone(server.state["postgres_last_success_utc"])

    def test_full_queue_drops_newest_without_blocking_sensor_status(self):
        self.writer.pending = queue.Queue(maxsize=1)
        self.writer.submit(reading())
        first = self.writer.pending.queue[0]
        with self.assertLogs(level="ERROR"):
            self.writer.submit(reading(temperature_c=99.0))
        self.assertIs(self.writer.pending.get_nowait(), first)
        self.assertEqual(server.state["postgres_batches_dropped"], 1)
        self.assertEqual(server.state["status"], "ok")

    def test_worker_redacts_failure_drops_without_retry_and_recovers(self):
        self.writer.submit(reading())
        self.writer.submit(reading(temperature_c=26.0))
        self.writer.finished.set()  # Drain queued work without waiting for more.
        original = self.writer.write_batch
        calls = []

        def fail_then_write(samples):
            calls.append(samples)
            if len(calls) == 1:
                raise RuntimeError("password=private-secret")
            original(samples)

        with patch.object(self.writer, "write_batch", side_effect=fail_then_write), \
                self.assertLogs(level="ERROR") as logs:
            self.writer.run()
        self.assertEqual(len(calls), 2)
        self.assertNotIn("private-secret", " ".join(logs.output))
        self.assertEqual(server.state["postgres_batches_dropped"], 1)
        self.assertEqual(server.state["postgres_batches_written"], 1)
        self.assertIsNone(server.state["postgres_last_error"])
        self.assertTrue(self.writer.pending.empty())
        self.assertEqual(self.writer.pending.unfinished_tasks, 0)
        self.connection.close.assert_called()

    def test_database_delay_does_not_block_recording_or_submitting(self):
        entered, release = threading.Event(), threading.Event()

        def blocked(samples):
            entered.set()
            release.wait(timeout=2)

        with patch.object(self.writer, "write_batch", side_effect=blocked):
            self.writer.start()
            try:
                self.writer.submit(reading())
                self.assertTrue(entered.wait(timeout=1))
                with patch.object(server, "PostgresWriter", return_value=self.writer):
                    loop = server.SensorLoop(MagicMock())
                loop._record_success(reading(temperature_c=27.0))
                self.writer.submit(reading(temperature_c=27.0))
                self.assertEqual(server.state["last_sample"]["values"]["temperature_c"], 27.0)
                self.assertEqual(self.writer.pending.qsize(), 1)
            finally:
                release.set()
                self.writer.close()

    def test_disabled_sink_needs_no_driver_or_connection(self):
        with patch.object(server, "DEFAULT_POSTGRES_ENABLED", False):
            writer = server.PostgresWriter(self.connect)
            writer.start()
            writer.submit(reading())
            writer.close()
        self.connect.assert_not_called()
        self.assertTrue(writer.pending.empty())

    def test_missing_postgres_driver_fails_startup_explicitly(self):
        with patch.dict(sys.modules, {"psycopg2": None}):
            with self.assertRaisesRegex(SystemExit, "python3-psycopg2"):
                server.PostgresWriter()

    def test_bundled_sensor_driver_import_never_opens_a_bus(self):
        bundled = Path(__file__).parents[1]
        with patch.object(server, "DEFAULT_SENSOR_REPO", bundled), \
                patch.object(sys, "path", list(sys.path)), patch.dict(sys.modules):
            sys.modules.pop("bme680", None)
            sys.modules.pop("bme680.constants", None)
            driver = server.BME680Driver()
            self.assertEqual(Path(driver.bme680.__file__).resolve(), bundled.resolve() / "bme680/__init__.py")
            self.assertTrue(callable(driver.bme680.BME680))

    def test_libpq_settings_and_timeouts_without_exposing_password(self):
        settings = dict(PGHOST="archive", PGPORT="5434", PGDATABASE="dcs_archive",
                        PGUSER="dcs_writer", PGPASSFILE="/protected/passfile")
        with patch.dict(os.environ, settings):
            self.writer.write_batch(server.postgres_samples(reading()))
        kwargs = self.connect.call_args.kwargs
        self.assertEqual(kwargs["host"], "archive")
        self.assertEqual(kwargs["passfile"], "/protected/passfile")
        self.assertEqual(kwargs["connect_timeout"], 5)
        self.assertIn("statement_timeout=5000", kwargs["options"])
        self.assertNotIn("password", kwargs)


if __name__ == "__main__":
    unittest.main()
