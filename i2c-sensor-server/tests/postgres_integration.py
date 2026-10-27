"""Exercise archive SQL on temporary tables only; pass collector source on stdin.

Run in a Python environment with psycopg2 and protected libpq settings. No
sensor imports, polling, production rows, or persistent schema changes.
"""
import json
import sys
import types
from unittest.mock import patch

import psycopg2


class TempCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    @staticmethod
    def temporary_sql(sql):
        return sql.replace("public.trk_channel", "pg_temp.i2c_test_channel").replace(
            "public.trk_value", "pg_temp.i2c_test_value")

    def execute(self, sql, args=None):
        return self.cursor.execute(self.temporary_sql(sql), args)

    def executemany(self, sql, args):
        return self.cursor.executemany(self.temporary_sql(sql), args)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class TempConnection:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def cursor(self):
        return TempCursor(self.connection.cursor())


def main():
    module = types.ModuleType("i2c_integration_subject")
    sys.modules[module.__name__] = module
    with patch.dict(sys.modules, {"smbus2": types.SimpleNamespace(SMBus=None)}):
        exec(compile(sys.stdin.read(), "i2c-sensor-server.py", "exec"), module.__dict__)
    connection = psycopg2.connect(
        connect_timeout=5, application_name="i2c-temporary-table-integration",
        options="-c statement_timeout=5000 -c lock_timeout=5000")
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TEMP TABLE i2c_test_channel "
                               "(LIKE public.trk_channel INCLUDING DEFAULTS INCLUDING IDENTITY "
                               "INCLUDING CONSTRAINTS INCLUDING INDEXES)")
                cursor.execute("CREATE TEMP TABLE i2c_test_value (LIKE public.trk_value)")
                cursor.execute("ALTER TABLE pg_temp.i2c_test_value ADD FOREIGN KEY (channel_id) "
                               "REFERENCES pg_temp.i2c_test_channel(id)")
                cursor.execute("ALTER TABLE pg_temp.i2c_test_value ADD CHECK (value < 1000000)")
        writer = module.PostgresWriter(connect=lambda **kwargs: None)
        writer.connection = TempConnection(connection)
        module.state["hostname"] = "mu2e-trk-psu13"
        reading = module.SensorReading("2026-10-27T21:00:00Z", "test", "bme680", {
            "temperature_c": 25.5, "pressure_hpa": 1001.2, "humidity_rh": 42.0,
            "dew_point_c": 11.3, "gas_resistance_ohms": 12345.0, "heat_stable": True}, "bme680")
        samples = module.postgres_samples(reading)
        writer.write_batch(samples)
        writer.write_batch(samples)  # Reuse committed metadata/cache.
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_temp.i2c_test_channel")
                assert cursor.fetchone()[0] == 6
                cursor.execute("SELECT count(*) FROM pg_temp.i2c_test_value")
                assert cursor.fetchone()[0] == 12
                cursor.execute("SELECT c.quantity,c.unit,v.value,v.time FROM pg_temp.i2c_test_value v "
                               "JOIN pg_temp.i2c_test_channel c ON c.id=v.channel_id ORDER BY c.id")
                rows = cursor.fetchall()
                for row, sample in zip(rows[::2], samples):
                    assert row == (sample[4], sample[3], sample[6], sample[5])
        bad_reading = module.SensorReading(reading.timestamp_utc, "test", "rollback_test",
                                          {"temperature_c": 1e9}, "bme680")
        try:
            writer.write_batch(module.postgres_samples(bad_reading))
        except psycopg2.errors.CheckViolation:
            pass
        else:
            raise AssertionError("Expected transaction failure")
        assert len(writer.channel_ids) == 6
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_temp.i2c_test_channel")
                assert cursor.fetchone()[0] == 6
                cursor.execute("SELECT count(*) FROM pg_temp.i2c_test_value")
                assert cursor.fetchone()[0] == 12
        print(json.dumps({"result": "passed", "temporary_channels": 6,
                          "temporary_values": 12, "rollback_verified": True,
                          "production_rows_written": 0}))
    finally:
        connection.close()  # All temporary tables disappear.


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Integration failed: " + type(exc).__name__)
        raise SystemExit(1) from None
