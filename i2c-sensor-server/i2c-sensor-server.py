#!/usr/bin/env python3
"""Generic I2C sensor polling service with pluggable sensor drivers."""

from __future__ import annotations

import json
import logging
import math
import os
import signal
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from smbus2 import SMBus
except ImportError as exc:  # pragma: no cover - import failure is runtime-specific
    raise SystemExit(
        "smbus2 is required. Install it with: sudo apt-get install -y python3-smbus"
    ) from exc

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
except ImportError:  # pragma: no cover - import failure is runtime-specific
    InfluxDBClient = None
    Point = None
    WritePrecision = None
    SYNCHRONOUS = None


SERVICE_NAME = "i2c-sensor-server"
DEFAULT_SENSOR_TYPE = os.getenv("I2C_SENSOR_SERVER_SENSOR_TYPE", "bme680").strip().lower()
DEFAULT_SENSOR_REPO = Path(
    os.getenv("I2C_SENSOR_SERVER_SENSOR_REPO", "/home/mu2e/vr-dev/bme680-python")
)
DEFAULT_HTTP_HOST = os.getenv("I2C_SENSOR_SERVER_HTTP_HOST", "0.0.0.0")
DEFAULT_HTTP_PORT = int(os.getenv("I2C_SENSOR_SERVER_HTTP_PORT", "12003"))
DEFAULT_LOG_PATH = Path(
    os.getenv(
        "I2C_SENSOR_SERVER_LOG_PATH",
        "/var/log/mu2e-tracker-i2c-sensor-tools/i2c-sensor.log",
    )
)
DEFAULT_BUFFER_SIZE = int(os.getenv("I2C_SENSOR_SERVER_BUFFER_SIZE", "256"))
DEFAULT_I2C_BUS = int(os.getenv("I2C_SENSOR_SERVER_I2C_BUS", "4"))
DEFAULT_I2C_ADDR = int(os.getenv("I2C_SENSOR_SERVER_I2C_ADDR", "0x76"), 0)
DEFAULT_PERIOD_S = float(os.getenv("I2C_SENSOR_SERVER_PERIOD_S", "20.0"))
DEFAULT_I2C_REOPEN_BACKOFF_S = float(
    os.getenv("I2C_SENSOR_SERVER_I2C_REOPEN_BACKOFF_S", "1.0")
)
DEFAULT_I2C_READ_RETRIES = int(os.getenv("I2C_SENSOR_SERVER_I2C_READ_RETRIES", "2"))
DEFAULT_MEASUREMENT = os.getenv("I2C_SENSOR_SERVER_MEASUREMENT", "env_sensor")
DEFAULT_INFLUX_URL = os.getenv("I2C_SENSOR_SERVER_INFLUX_URL", "http://localhost:8086")
DEFAULT_INFLUX_ORG = os.getenv("I2C_SENSOR_SERVER_INFLUX_ORG", "mu2e")
DEFAULT_INFLUX_BUCKET = os.getenv("I2C_SENSOR_SERVER_INFLUX_BUCKET", "tracker-env")
DEFAULT_INFLUX_TOKEN = os.getenv("I2C_SENSOR_SERVER_INFLUX_TOKEN", "")
DEFAULT_NO_DATA_STREAK_TRIGGER = int(
    os.getenv("I2C_SENSOR_SERVER_NO_DATA_STREAK_TRIGGER", "5")
)


running = True
state_lock = threading.Lock()
http_server = None
state: dict[str, object] = {
    "service": SERVICE_NAME,
    "sensor_type": DEFAULT_SENSOR_TYPE,
    "hostname": socket.gethostname(),
    "started_at_utc": None,
    "status": "starting",
    "i2c_bus": DEFAULT_I2C_BUS,
    "i2c_address": f"0x{DEFAULT_I2C_ADDR:02x}",
    "period_s": DEFAULT_PERIOD_S,
    "measurement": DEFAULT_MEASUREMENT,
    "influx_enabled": bool(DEFAULT_INFLUX_TOKEN),
    "sensor_repo": str(DEFAULT_SENSOR_REPO),
    "supported_sensor_types": ["bme680"],
    "last_sample": None,
    "last_error": None,
    "last_attempt_utc": None,
    "last_success_utc": None,
    "sample_count": 0,
    "no_data_streak": 0,
}
sample_history: deque[dict[str, object]] = deque(maxlen=DEFAULT_BUFFER_SIZE)


@dataclass(frozen=True)
class SensorReading:
    timestamp_utc: str
    timestamp_local: str
    sensor_type: str
    values: dict[str, object]
    source: str


class SensorDriver:
    sensor_type = "unknown"
    source = "unknown"

    def configure(self, _sensor) -> None:
        raise NotImplementedError

    def read(self, _sensor) -> SensorReading | None:
        raise NotImplementedError


class BME680Driver(SensorDriver):
    sensor_type = "bme680"
    source = "bme680"

    def __init__(self) -> None:
        repo = DEFAULT_SENSOR_REPO
        if (repo / "bme680").exists():
            sys.path.insert(0, str(repo))
        try:
            import bme680  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime-specific
            raise SystemExit(
                "bme680 module is required for sensor_type=bme680. "
                "Install pimoroni/bme680-python or set I2C_SENSOR_SERVER_SENSOR_REPO."
            ) from exc
        self.bme680 = bme680

    def create_sensor(self, bus: SMBus):
        return self.bme680.BME680(i2c_addr=DEFAULT_I2C_ADDR, i2c_device=bus)

    def configure(self, sensor) -> None:
        sensor.set_humidity_oversample(self.bme680.OS_2X)
        sensor.set_pressure_oversample(self.bme680.OS_4X)
        sensor.set_temperature_oversample(self.bme680.OS_8X)
        sensor.set_filter(self.bme680.FILTER_SIZE_3)

    def read(self, sensor) -> SensorReading | None:
        if not sensor.get_sensor_data():
            return None

        temperature_c = float(sensor.data.temperature)
        pressure_hpa = float(sensor.data.pressure)
        humidity_rh = float(sensor.data.humidity)
        heat_stable = bool(getattr(sensor.data, "heat_stable", False))
        gas_resistance_ohms = None
        if heat_stable:
            gas_resistance_ohms = float(sensor.data.gas_resistance)

        values = {
            "temperature_c": temperature_c,
            "pressure_hpa": pressure_hpa,
            "humidity_rh": humidity_rh,
            "dew_point_c": dew_point_c(temperature_c, humidity_rh),
            "gas_resistance_ohms": gas_resistance_ohms,
            "heat_stable": heat_stable,
        }
        return SensorReading(
            timestamp_utc=utc_now_text(),
            timestamp_local=local_now_text(),
            sensor_type=self.sensor_type,
            values=values,
            source=self.source,
        )

    def influx_fields(self, reading: SensorReading) -> dict[str, float]:
        fields = {}
        mapping = {
            "temperature_c": "temperature_C",
            "pressure_hpa": "pressure_hPa",
            "humidity_rh": "humidity_RH",
            "dew_point_c": "dew_point",
            "gas_resistance_ohms": "gas_resistance_ohms",
        }
        for key, field_name in mapping.items():
            value = reading.values.get(key)
            if value is not None:
                fields[field_name] = float(value)
        return fields


def get_driver() -> SensorDriver:
    if DEFAULT_SENSOR_TYPE == "bme680":
        return BME680Driver()
    raise SystemExit(
        f"unsupported sensor type {DEFAULT_SENSOR_TYPE!r}; "
        f"supported types: {', '.join(state['supported_sensor_types'])}"
    )


def handle_signal(signum: int, _frame) -> None:
    global running
    running = False
    logging.info("received signal %s, shutting down", signum)


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_now_text() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def dew_point_c(temp_c: float, rh: float) -> float | None:
    if rh <= 0:
        return None
    a = 17.62
    b = 243.12
    gamma = math.log(rh / 100.0) + (a * temp_c) / (b + temp_c)
    return (b * gamma) / (a - gamma)


class InfluxWriter:
    def __init__(self, driver: BME680Driver) -> None:
        self.driver = driver
        self.client = None
        self.write_api = None
        if not DEFAULT_INFLUX_TOKEN:
            logging.info("influx disabled: no token configured")
            return
        if InfluxDBClient is None:
            logging.warning("influx disabled: influxdb-client not installed")
            return
        self.client = InfluxDBClient(
            url=DEFAULT_INFLUX_URL,
            token=DEFAULT_INFLUX_TOKEN,
            org=DEFAULT_INFLUX_ORG,
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    @property
    def enabled(self) -> bool:
        return self.write_api is not None

    def write(self, reading: SensorReading) -> None:
        if self.write_api is None:
            return
        timestamp = datetime.fromisoformat(reading.timestamp_utc.replace("Z", "+00:00"))
        point = (
            Point(DEFAULT_MEASUREMENT)
            .tag("host", state["hostname"])
            .tag("sensor_type", reading.sensor_type)
            .tag("source", reading.source)
            .time(timestamp, WritePrecision.NS)
        )
        for field_name, value in self.driver.influx_fields(reading).items():
            point = point.field(field_name, value)
        self.write_api.write(
            bucket=DEFAULT_INFLUX_BUCKET,
            org=DEFAULT_INFLUX_ORG,
            record=point,
        )

    def close(self) -> None:
        if self.client is not None:
            self.client.close()


class SensorLoop:
    def __init__(self, driver: BME680Driver) -> None:
        self.driver = driver
        self.bus = None
        self.sensor = None
        self.influx = InfluxWriter(driver)
        with state_lock:
            state["influx_enabled"] = self.influx.enabled

    def open_sensor(self) -> None:
        self.bus = SMBus(DEFAULT_I2C_BUS)
        self.sensor = self.driver.create_sensor(self.bus)
        self.driver.configure(self.sensor)
        logging.info(
            "sensor initialized type=%s bus=%s addr=0x%02x repo=%s",
            self.driver.sensor_type,
            DEFAULT_I2C_BUS,
            DEFAULT_I2C_ADDR,
            DEFAULT_SENSOR_REPO,
        )

    def close_bus(self) -> None:
        try:
            if self.bus is not None:
                self.bus.close()
        except Exception:
            pass
        self.bus = None
        self.sensor = None

    def _set_error(self, message: str) -> None:
        with state_lock:
            state["status"] = "error"
            state["last_error"] = message

    def _set_attempt_time(self) -> None:
        with state_lock:
            state["last_attempt_utc"] = utc_now_text()

    def _record_success(self, reading: SensorReading) -> None:
        payload = {
            "timestamp_utc": reading.timestamp_utc,
            "timestamp_local": reading.timestamp_local,
            "sensor_type": reading.sensor_type,
            "values": reading.values,
            "source": reading.source,
        }
        with state_lock:
            state["status"] = "ok"
            state["last_error"] = None
            state["last_sample"] = payload
            state["last_success_utc"] = reading.timestamp_utc
            state["sample_count"] = int(state["sample_count"]) + 1
            state["no_data_streak"] = 0
            sample_history.appendleft(payload)

    def _record_no_data(self) -> None:
        with state_lock:
            streak = int(state["no_data_streak"]) + 1
            state["status"] = "no-data"
            state["no_data_streak"] = streak
        logging.warning("no data streak=%s/%s", streak, DEFAULT_NO_DATA_STREAK_TRIGGER)
        if streak >= DEFAULT_NO_DATA_STREAK_TRIGGER:
            with state_lock:
                state["no_data_streak"] = DEFAULT_NO_DATA_STREAK_TRIGGER

    def run(self) -> None:
        try:
            self.open_sensor()
        except Exception as exc:
            self._set_error(f"failed to initialize sensor: {exc!r}")
            logging.exception("failed to initialize sensor")

        while running:
            self._set_attempt_time()
            reading = None
            for attempt in range(DEFAULT_I2C_READ_RETRIES + 1):
                try:
                    if self.sensor is None:
                        self.open_sensor()
                    reading = self.driver.read(self.sensor)
                    break
                except OSError as exc:
                    logging.warning(
                        "i2c read error attempt=%s/%s err=%r -> reopening bus",
                        attempt + 1,
                        DEFAULT_I2C_READ_RETRIES + 1,
                        exc,
                    )
                    self.close_bus()
                    time.sleep(DEFAULT_I2C_REOPEN_BACKOFF_S)
                    try:
                        self.open_sensor()
                    except Exception as reopen_exc:
                        self._set_error(f"failed to reopen sensor: {reopen_exc!r}")
                        logging.exception("failed to reopen sensor")
                except Exception as exc:
                    self._set_error(f"sensor read failed: {exc!r}")
                    logging.exception("sensor read failed")
                    break

            if reading is None:
                self._record_no_data()
                time.sleep(DEFAULT_PERIOD_S)
                continue

            self._record_success(reading)
            try:
                self.influx.write(reading)
            except Exception as exc:
                logging.error("influx write error err=%r", exc)

            logging.info(
                "sample utc=%s type=%s values=%s",
                reading.timestamp_utc,
                reading.sensor_type,
                json.dumps(reading.values, sort_keys=True),
            )
            time.sleep(DEFAULT_PERIOD_S)

        self.close_bus()
        self.influx.close()


class I2CSensorHandler(BaseHTTPRequestHandler):
    server_version = "I2CSensorServer/1.0"

    def log_message(self, fmt: str, *args) -> None:
        logging.info("http %s - %s", self.address_string(), fmt % args)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            with state_lock:
                payload = dict(state)
                payload["history_size"] = len(sample_history)
            self._send_json(payload)
            return
        if parsed.path in ("/readings", "/samples"):
            params = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit", ["20"])[0])
            except ValueError:
                self._send_json({"error": "limit must be an integer"}, status=HTTPStatus.BAD_REQUEST)
                return
            limit = max(1, min(limit, DEFAULT_BUFFER_SIZE))
            with state_lock:
                payload = {
                    "service": SERVICE_NAME,
                    "sensor_type": state["sensor_type"],
                    "hostname": state["hostname"],
                    "readings": list(sample_history)[:limit],
                    "returned": min(limit, len(sample_history)),
                }
            self._send_json(payload)
            return
        self._send_json({"error": "not found", "path": parsed.path}, status=HTTPStatus.NOT_FOUND)


def start_http_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT), I2CSensorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="http-server")
    thread.start()
    logging.info("http server listening host=%s port=%s", DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT)
    return server


def main() -> int:
    global http_server
    configure_logging(DEFAULT_LOG_PATH)

    with state_lock:
        state["started_at_utc"] = utc_now_text()

    logging.info("starting %s sensor_type=%s", SERVICE_NAME, DEFAULT_SENSOR_TYPE)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    driver = get_driver()
    sensor_thread = threading.Thread(
        target=SensorLoop(driver).run,
        daemon=True,
        name="sensor-loop",
    )
    sensor_thread.start()
    http_server = start_http_server()

    try:
        while running:
            time.sleep(0.5)
    finally:
        if http_server is not None:
            http_server.shutdown()
            http_server.server_close()
        sensor_thread.join(timeout=5.0)

    logging.info("%s stopped", SERVICE_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
