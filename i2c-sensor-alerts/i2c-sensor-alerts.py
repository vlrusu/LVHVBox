#!/usr/bin/env python3
"""Pushover alert service for the I2C sensor HTTP API."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import struct
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

try:
    import requests
except ImportError as exc:  # pragma: no cover - import failure is runtime-specific
    raise SystemExit(
        "requests is required. Install it with: sudo apt-get install -y python3-requests"
    ) from exc


DEFAULT_LOG_PATH = Path(
    os.getenv(
        "I2C_SENSOR_ALERTS_LOG_PATH",
        "/var/log/mu2e-tracker-i2c-sensor-tools/i2c-sensor-alerts.log",
    )
)
DEFAULT_SENSOR_URL = os.getenv("I2C_SENSOR_ALERTS_SENSOR_URL", "http://127.0.0.1:12003/health")
DEFAULT_PERIOD_S = float(os.getenv("I2C_SENSOR_ALERTS_PERIOD_S", "30.0"))
DEFAULT_TEMP_HIGH_C = float(os.getenv("I2C_SENSOR_ALERTS_TEMP_HIGH_C", "28.0"))
DEFAULT_HUMID_HIGH_RH = float(os.getenv("I2C_SENSOR_ALERTS_HUMID_HIGH_RH", "60.0"))
DEFAULT_DEW_POINT_THRESHOLD_C = float(os.getenv("I2C_SENSOR_ALERTS_DEW_POINT_THRESHOLD_C", "18.0"))
DEFAULT_DEWPOINT_APPROACH_MARGIN_C = float(
    os.getenv("I2C_SENSOR_ALERTS_DEWPOINT_APPROACH_MARGIN_C", "5.0")
)
DEFAULT_ALERT_COOLDOWN_S = float(
    os.getenv("I2C_SENSOR_ALERTS_ALERT_COOLDOWN_S", str(20 * 60))
)
DEFAULT_CONDITION_STREAK_TRIGGER = int(
    os.getenv("I2C_SENSOR_ALERTS_CONDITION_STREAK_TRIGGER", "3")
)
DEFAULT_NO_DATA_STREAK_TRIGGER = int(
    os.getenv("I2C_SENSOR_ALERTS_NO_DATA_STREAK_TRIGGER", "5")
)
DEFAULT_NO_DATA_ALERT_COOLDOWN_S = float(
    os.getenv("I2C_SENSOR_ALERTS_NO_DATA_ALERT_COOLDOWN_S", str(6 * 60 * 60))
)
DEFAULT_PUSHOVER_USER_KEY = os.getenv("I2C_SENSOR_ALERTS_PUSHOVER_USER_KEY", "")
DEFAULT_PUSHOVER_API_TOKEN = os.getenv("I2C_SENSOR_ALERTS_PUSHOVER_API_TOKEN", "")
DEFAULT_LVHV_HOST_PREFIX = os.getenv("I2C_SENSOR_ALERTS_LVHV_HOST_PREFIX", "mu2e-trk-psu")
DEFAULT_LVHV_HOST_SUFFIX = os.getenv("I2C_SENSOR_ALERTS_LVHV_HOST_SUFFIX", "")
DEFAULT_LVHV_HOST_START = int(os.getenv("I2C_SENSOR_ALERTS_LVHV_HOST_START", "0"))
DEFAULT_LVHV_HOST_STOP = int(os.getenv("I2C_SENSOR_ALERTS_LVHV_HOST_STOP", "17"))
DEFAULT_LVHV_PORT = int(os.getenv("I2C_SENSOR_ALERTS_LVHV_PORT", "12000"))
DEFAULT_LVHV_COMMANDS_PATH = Path(
    os.getenv("I2C_SENSOR_ALERTS_LVHV_COMMANDS_PATH", "/etc/mu2e-tracker-lvhv-tools/commands.h")
)
DEFAULT_LVHV_POWEROFF_CHANNEL = int(
    os.getenv("I2C_SENSOR_ALERTS_LVHV_POWEROFF_CHANNEL", "6")
)

running = True
last_alert_ts: dict[str, float] = {}
no_data_streak = 0
last_seen_sample_ts = None
shutdown_condition_active: dict[str, bool] = {}
condition_streaks: dict[str, int] = {}
runtime_args = None


def handle_signal(signum: int, _frame) -> None:
    global running
    running = False
    logging.info("received signal %s, shutting down", signum)


def parse_args():
    parser = argparse.ArgumentParser(description="I2C sensor alerting and fleet shutdown service")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate alert and shutdown logic without sending powerOff or Pushover",
    )
    return parser.parse_args()


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


def can_alert(key: str, now: float, cooldown_s: float) -> bool:
    last = last_alert_ts.get(key, 0.0)
    return (now - last) >= cooldown_s


def pushover_send(title: str, message: str, priority: int = 0) -> None:
    if runtime_args is not None and runtime_args.dry_run:
        logging.warning(
            "dry-run: would send pushover title=%r priority=%s message=%r",
            title,
            priority,
            message,
        )
        return
    if not (DEFAULT_PUSHOVER_API_TOKEN and DEFAULT_PUSHOVER_USER_KEY):
        logging.warning("pushover skipped: credentials not configured")
        return

    payload = {
        "token": DEFAULT_PUSHOVER_API_TOKEN,
        "user": DEFAULT_PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "priority": str(priority),
    }
    response = requests.post(
        "https://api.pushover.net/1/messages.json",
        timeout=10,
        data=payload,
    )
    response.raise_for_status()


class FleetPowerOffClient:
    def __init__(self, commands_path: Path):
        self.command_codes = self._read_command_codes(commands_path)

    def _read_command_codes(self, commands_path: Path) -> dict[str, int]:
        command_codes = {}
        with commands_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.split("//", 1)[0].strip()
                if not line:
                    continue
                tokens = line.split()
                if len(tokens) >= 3 and tokens[0] == "#define":
                    command_codes[tokens[1]] = int(tokens[2], 0)
        required = ("COMMAND_powerOff", "TYPE_lv")
        missing = [key for key in required if key not in command_codes]
        if missing:
            raise RuntimeError(
                f"missing required command codes in {commands_path}: {', '.join(missing)}"
            )
        return command_codes

    def _encode_block(self, typecode: str, payload: bytes, count: int) -> bytes:
        return struct.pack("=cI", typecode.encode("ascii"), count) + payload

    def _encode_message(self) -> bytes:
        blocks = [
            self._encode_block("C", b"LVHV", 4),
            self._encode_block(
                "U",
                struct.pack("I", self.command_codes["COMMAND_powerOff"]),
                1,
            ),
            self._encode_block(
                "U",
                struct.pack("I", self.command_codes["TYPE_lv"]),
                1,
            ),
            self._encode_block("C", bytes((DEFAULT_LVHV_POWEROFF_CHANNEL,)), 1),
            self._encode_block("F", struct.pack("f", 0.0), 1),
        ]
        return struct.pack("I", len(blocks)) + b"".join(blocks)

    def _recv_exact(self, connection: socket.socket, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining > 0:
            chunk = connection.recv(remaining)
            if not chunk:
                raise RuntimeError("lvhv-server closed the connection before replying")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_reply(self, connection: socket.socket) -> None:
        block_count = struct.unpack("I", self._recv_exact(connection, 4))[0]
        for _ in range(block_count):
            typecode = self._recv_exact(connection, 1).decode("ascii")
            count = struct.unpack("I", self._recv_exact(connection, 4))[0]
            payload_size = count * struct.calcsize(
                {"C": "c", "I": "i", "U": "I", "F": "f", "D": "d"}[typecode]
            )
            self._recv_exact(connection, payload_size)

    def power_off_host(self, host: str) -> None:
        message = self._encode_message()
        with socket.create_connection((host, DEFAULT_LVHV_PORT), timeout=5.0) as connection:
            connection.settimeout(5.0)
            connection.sendall(message)
            self._read_reply(connection)


def build_fleet_hosts() -> list[str]:
    return [
        f"{DEFAULT_LVHV_HOST_PREFIX}{index}{DEFAULT_LVHV_HOST_SUFFIX}"
        for index in range(DEFAULT_LVHV_HOST_START, DEFAULT_LVHV_HOST_STOP + 1)
    ]


def send_global_poweroff(reason_text: str) -> None:
    if runtime_args is not None and runtime_args.dry_run:
        for host in build_fleet_hosts():
            logging.warning(
                "dry-run: would issue powerOff to host=%s channel=%s reason=%s",
                host,
                DEFAULT_LVHV_POWEROFF_CHANNEL,
                reason_text,
            )
        return

    client = FleetPowerOffClient(DEFAULT_LVHV_COMMANDS_PATH)
    hosts = build_fleet_hosts()
    failures = []
    for host in hosts:
        try:
            client.power_off_host(host)
            logging.warning("issued powerOff to host=%s channel=%s", host, DEFAULT_LVHV_POWEROFF_CHANNEL)
        except Exception as exc:
            failures.append((host, repr(exc)))
            logging.error("failed powerOff host=%s err=%r", host, exc)

    if failures:
        summary = ", ".join(f"{host}: {err}" for host, err in failures)
        logging.error("global powerOff completed with failures reason=%s failures=%s", reason_text, summary)
    else:
        logging.warning("global powerOff completed for all hosts reason=%s", reason_text)


def enforce_shutdown_if_needed(reason_key: str, reason_text: str) -> None:
    active = shutdown_condition_active.get(reason_key, False)
    send_global_poweroff(reason_text)
    if not active:
        logging.warning("set shutdown latch key=%s", reason_key)
    shutdown_condition_active[reason_key] = True


def clear_shutdown_condition(reason_key: str) -> None:
    if shutdown_condition_active.get(reason_key, False):
        logging.info("cleared shutdown latch key=%s", reason_key)
    shutdown_condition_active[reason_key] = False


def reset_condition(reason_key: str) -> None:
    if condition_streaks.get(reason_key, 0):
        logging.info("cleared condition streak key=%s", reason_key)
    condition_streaks[reason_key] = 0
    clear_shutdown_condition(reason_key)


def condition_ready(reason_key: str, reason_text: str) -> bool:
    streak = condition_streaks.get(reason_key, 0) + 1
    condition_streaks[reason_key] = streak
    if streak < DEFAULT_CONDITION_STREAK_TRIGGER:
        logging.warning(
            "condition pending key=%s streak=%s/%s reason=%s",
            reason_key,
            streak,
            DEFAULT_CONDITION_STREAK_TRIGGER,
            reason_text,
        )
        return False
    condition_streaks[reason_key] = DEFAULT_CONDITION_STREAK_TRIGGER
    return True


def fetch_health() -> dict[str, object]:
    with urlopen(DEFAULT_SENSOR_URL, timeout=10.0) as response:
        return json.load(response)


def alert_no_data_if_needed(hostname: str, status: str) -> None:
    now = time.time()
    enforce_shutdown_if_needed(
        "no_data",
        f"no_data status={status} url={DEFAULT_SENSOR_URL}",
    )
    if can_alert("no_data", now, DEFAULT_NO_DATA_ALERT_COOLDOWN_S):
        pushover_send(
            title=f"[{hostname}] I2C SENSOR NO DATA",
            message=(
                f"Sensor service returned status={status!s} "
                f"{DEFAULT_NO_DATA_STREAK_TRIGGER} times in a row from {DEFAULT_SENSOR_URL}."
            ),
        )
        last_alert_ts["no_data"] = now


def alert_if_needed(hostname: str, sensor_type: str, values: dict[str, object]) -> None:
    now = time.time()
    temperature_c = values.get("temperature_c")
    humidity_rh = values.get("humidity_rh")
    dew_point = values.get("dew_point_c")

    if isinstance(temperature_c, (float, int)) and temperature_c > DEFAULT_TEMP_HIGH_C:
        reason_text = f"temp_high sensor_type={sensor_type} temperature_c={temperature_c:.2f}"
        if condition_ready("temp_high", reason_text):
            enforce_shutdown_if_needed("temp_high", reason_text)
            if can_alert("temp_high", now, DEFAULT_ALERT_COOLDOWN_S):
                pushover_send(
                    title=f"[{hostname}] {sensor_type} TEMP HIGH",
                    message=f"Temperature {temperature_c:.2f} C exceeds {DEFAULT_TEMP_HIGH_C:.2f} C",
                )
                last_alert_ts["temp_high"] = now
    else:
        reset_condition("temp_high")

    if isinstance(humidity_rh, (float, int)) and humidity_rh > DEFAULT_HUMID_HIGH_RH:
        reason_text = f"humid_high sensor_type={sensor_type} humidity_rh={humidity_rh:.2f}"
        if condition_ready("humid_high", reason_text):
            enforce_shutdown_if_needed("humid_high", reason_text)
            if can_alert("humid_high", now, DEFAULT_ALERT_COOLDOWN_S):
                pushover_send(
                    title=f"[{hostname}] {sensor_type} HUMIDITY HIGH",
                    message=f"Humidity {humidity_rh:.2f}% exceeds {DEFAULT_HUMID_HIGH_RH:.2f}%",
                )
                last_alert_ts["humid_high"] = now
    else:
        reset_condition("humid_high")

    if isinstance(dew_point, (float, int)):
        trigger_level = DEFAULT_DEW_POINT_THRESHOLD_C - DEFAULT_DEWPOINT_APPROACH_MARGIN_C
        if dew_point >= trigger_level:
            reason_text = f"dew_approach sensor_type={sensor_type} dew_point_c={dew_point:.2f}"
            if condition_ready("dew_approach", reason_text):
                enforce_shutdown_if_needed("dew_approach", reason_text)
                if can_alert("dew_approach", now, DEFAULT_ALERT_COOLDOWN_S):
                    pushover_send(
                        title=f"[{hostname}] {sensor_type} DEW POINT APPROACHING LIMIT",
                        message=(
                            f"Dew point {dew_point:.2f} C is within "
                            f"{DEFAULT_DEWPOINT_APPROACH_MARGIN_C:.1f} C of threshold "
                            f"{DEFAULT_DEW_POINT_THRESHOLD_C:.2f} C"
                        ),
                        priority=1,
                    )
                    last_alert_ts["dew_approach"] = now
        else:
            reset_condition("dew_approach")
    else:
        reset_condition("dew_approach")


def main() -> int:
    global no_data_streak, last_seen_sample_ts, runtime_args

    runtime_args = parse_args()

    configure_logging(DEFAULT_LOG_PATH)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    logging.info(
        "starting i2c-sensor-alerts sensor_url=%s lvhv_hosts=%s..%s prefix=%s suffix=%s port=%s condition_trigger_streak=%s no_data_trigger_streak=%s dry_run=%s",
        DEFAULT_SENSOR_URL,
        DEFAULT_LVHV_HOST_START,
        DEFAULT_LVHV_HOST_STOP,
        DEFAULT_LVHV_HOST_PREFIX,
        DEFAULT_LVHV_HOST_SUFFIX,
        DEFAULT_LVHV_PORT,
        DEFAULT_CONDITION_STREAK_TRIGGER,
        DEFAULT_NO_DATA_STREAK_TRIGGER,
        runtime_args.dry_run,
    )

    while running:
        try:
            payload = fetch_health()
            hostname = str(payload.get("hostname") or "unknown-host")
            sensor_type = str(payload.get("sensor_type") or "sensor")
            status = str(payload.get("status") or "unknown")
            sample = payload.get("last_sample") or {}
            sample_ts = sample.get("timestamp_utc")

            if status != "ok" or not sample_ts or sample_ts == last_seen_sample_ts:
                no_data_streak += 1
                logging.warning(
                    "no fresh data streak=%s/%s status=%s sample_ts=%s",
                    no_data_streak,
                    DEFAULT_NO_DATA_STREAK_TRIGGER,
                    status,
                    sample_ts,
                )
                if no_data_streak >= DEFAULT_NO_DATA_STREAK_TRIGGER:
                    alert_no_data_if_needed(hostname, status)
                    no_data_streak = DEFAULT_NO_DATA_STREAK_TRIGGER
            else:
                no_data_streak = 0
                last_alert_ts.pop("no_data", None)
                clear_shutdown_condition("no_data")
                last_seen_sample_ts = sample_ts
                values = sample.get("values") or {}
                alert_if_needed(hostname, sensor_type, values)
                logging.info(
                    "checked sample sensor_type=%s timestamp=%s",
                    sensor_type,
                    sample_ts,
                )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            no_data_streak += 1
            logging.error("health fetch failed streak=%s err=%r", no_data_streak, exc)
            if no_data_streak >= DEFAULT_NO_DATA_STREAK_TRIGGER:
                alert_no_data_if_needed("unknown-host", f"fetch_error:{type(exc).__name__}")
                no_data_streak = DEFAULT_NO_DATA_STREAK_TRIGGER
        except Exception as exc:
            logging.exception("unexpected alert loop error: %r", exc)

        time.sleep(DEFAULT_PERIOD_S)

    logging.info("i2c-sensor-alerts stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
