#!/usr/bin/env python3
"""Monitor Raspberry Pi health GPIOs and log AC power events."""

from __future__ import annotations

import configparser
import ctypes
import ipaddress
import json
import logging
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import gpiod
    from gpiod.line import Bias, Direction, Edge
except ImportError as exc:  # pragma: no cover - import failure is runtime-specific
    raise SystemExit(
        "python3-gpiod is required. Install it with: sudo apt-get install -y python3-gpiod"
    ) from exc

try:
    import smbus
except ImportError:  # pragma: no cover - import failure is runtime-specific
    smbus = None


DEFAULT_GPIO_CHIP = os.getenv("PI_HEALTH_GPIO_CHIP", "/dev/gpiochip0")
DEFAULT_GPIO6_LINE = int(os.getenv("PI_HEALTH_AC_GPIO6_LINE", "6"))
DEFAULT_GPIO6_ACTIVE_LOW = os.getenv("PI_HEALTH_GPIO6_ACTIVE_LOW", "0").lower() not in {
    "0",
    "false",
    "no",
}
DEFAULT_GPIO21_LINE = int(os.getenv("PI_HEALTH_ACFAIL_GPIO21_LINE", "21"))
DEFAULT_GPIO21_ACTIVE_LOW = os.getenv("PI_HEALTH_GPIO21_ACTIVE_LOW", "0").lower() not in {
    "0",
    "false",
    "no",
}
DEFAULT_X728_POWER_LINE = int(os.getenv("PI_HEALTH_X728_POWER_GPIO5_LINE", "5"))
DEFAULT_LOG_PATH = Path(
    os.getenv("PI_HEALTH_LOG_PATH", "/var/log/m2ue-tracker-pi-health-tools/ac-power-events.log")
)
DEFAULT_CONSUMER = os.getenv("PI_HEALTH_GPIO_CONSUMER", "pi-health-server")
DEFAULT_HTTP_HOST = os.getenv("PI_HEALTH_HTTP_HOST", "0.0.0.0")
DEFAULT_HTTP_PORT = int(os.getenv("PI_HEALTH_HTTP_PORT", "12002"))
DEFAULT_EVENT_BUFFER_SIZE = int(os.getenv("PI_HEALTH_EVENT_BUFFER_SIZE", "256"))
DEFAULT_I2C_BUS = int(os.getenv("PI_HEALTH_I2C_BUS", "1"))
DEFAULT_BATTERY_I2C_ADDRESS = int(
    os.getenv("PI_HEALTH_BATTERY_I2C_ADDRESS", "0x36"),
    0,
)
DEFAULT_ACTION_CONFIG_PATH = Path(
    os.getenv("PI_HEALTH_ACTION_CONFIG_PATH", "/etc/mu2e-tracker-pi-health-tools/actions.ini")
)
DEFAULT_LVHV_HOST = "127.0.0.1"
DEFAULT_LVHV_PORT = 12000
DEFAULT_LVHV_COMMANDS_PATH = Path("/etc/mu2e-tracker-lvhv-tools/commands.h")
DEFAULT_LVHV_POWEROFF_CHANNEL = 6
DEFAULT_GPIO21_REPEAT_WINDOW_SECONDS = 10.0
DEFAULT_X728_SOFT_SHUTDOWN_LINE = 26
DEFAULT_X728_SOFT_SHUTDOWN_PULSE_SECONDS = 2.0
DEFAULT_X728_SHUTDOWN_COMMAND = Path("/usr/local/bin/x728-shutdown")
DEFAULT_X728_REBOOT_PULSE_MINIMUM_SECONDS = 0.2
DEFAULT_X728_SHUTDOWN_PULSE_MINIMUM_SECONDS = 0.6
DEFAULT_SYSTEMCTL_PATH = "/usr/bin/systemctl"


running = True
state_lock = threading.Lock()
event_history = deque(maxlen=DEFAULT_EVENT_BUFFER_SIZE)
current_state = None
input_states = {}
started_at_utc = None
http_server = None
power_action_lock = threading.Lock()
gpio21_last_loss_monotonic = None
soft_shutdown_lock = threading.Lock()
soft_shutdown_status = {
    "state": "idle",
    "requested_at_utc": None,
    "error": None,
}
x728_power_status = {
    "gpio_line": DEFAULT_X728_POWER_LINE,
    "state": "idle",
    "pulse_started_at_utc": None,
    "last_pulse_seconds": None,
    "last_action": None,
    "last_action_at_utc": None,
    "error": None,
}
x728_power_lock = threading.Lock()


@dataclass(frozen=True)
class PowerActionConfig:
    gpio21_repeat_window_seconds: float
    lvhv_host: str
    lvhv_port: int
    lvhv_commands_path: Path
    lvhv_poweroff_channel: int
    x728_soft_shutdown_line: int
    x728_soft_shutdown_pulse_seconds: float
    x728_reboot_pulse_minimum_seconds: float
    x728_shutdown_pulse_minimum_seconds: float
    systemctl_path: Path


def handle_signal(signum: int, _frame) -> None:
    global running
    running = False
    logging.info("received signal %s, shutting down", signum)


@dataclass(frozen=True)
class AcPowerState:
    signal_name: str
    line_offset: int
    present: bool
    raw_value: int
    source: str
    event_name: str
    local_time: str
    utc_time: str


@dataclass(frozen=True)
class BatteryStatus:
    voltage_v: float | None
    capacity_pct: float | None
    source: str
    error: str | None = None


class LvhvPowerOffClient:
    def __init__(self, config: PowerActionConfig):
        self.config = config
        self._command_codes = self._read_command_codes(config.lvhv_commands_path)

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
            joined = ", ".join(missing)
            raise RuntimeError(f"missing required command codes in {commands_path}: {joined}")
        return command_codes

    def _encode_block(self, typecode: str, payload: bytes, count: int) -> bytes:
        return struct.pack("=cI", typecode.encode("ascii"), count) + payload

    def _encode_message(self) -> bytes:
        channel = self.config.lvhv_poweroff_channel
        blocks = [
            self._encode_block("C", b"LVHV", 4),
            self._encode_block(
                "U",
                struct.pack("I", self._command_codes["COMMAND_powerOff"]),
                1,
            ),
            self._encode_block(
                "U",
                struct.pack("I", self._command_codes["TYPE_lv"]),
                1,
            ),
            self._encode_block("C", bytes((channel,)), 1),
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
                {
                    "C": "c",
                    "I": "i",
                    "U": "I",
                    "F": "f",
                    "D": "d",
                }[typecode]
            )
            self._recv_exact(connection, payload_size)

    def power_off(self, reason: str) -> None:
        message = self._encode_message()
        with socket.create_connection(
            (self.config.lvhv_host, self.config.lvhv_port),
            timeout=5.0,
        ) as connection:
            connection.settimeout(5.0)
            connection.sendall(message)
            self._read_reply(connection)
        logging.warning(
            "issued powerOff to lvhv-server host=%s port=%s channel=%s reason=%s",
            self.config.lvhv_host,
            self.config.lvhv_port,
            self.config.lvhv_poweroff_channel,
            reason,
        )


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


def load_action_config(config_path: Path) -> PowerActionConfig:
    parser = configparser.ConfigParser()
    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
    section = parser["power_actions"] if parser.has_section("power_actions") else {}

    def get_string(option: str, default: str) -> str:
        value = os.getenv(f"PI_HEALTH_{option.upper()}")
        if value is not None:
            return value
        return str(section.get(option, default))

    def get_int(option: str, default: int) -> int:
        return int(get_string(option, str(default)))

    def get_float(option: str, default: float) -> float:
        return float(get_string(option, str(default)))

    return PowerActionConfig(
        gpio21_repeat_window_seconds=get_float(
            "gpio21_repeat_window_seconds",
            DEFAULT_GPIO21_REPEAT_WINDOW_SECONDS,
        ),
        lvhv_host=get_string("lvhv_host", DEFAULT_LVHV_HOST),
        lvhv_port=get_int("lvhv_port", DEFAULT_LVHV_PORT),
        lvhv_commands_path=Path(
            get_string("lvhv_commands_path", str(DEFAULT_LVHV_COMMANDS_PATH))
        ),
        lvhv_poweroff_channel=get_int(
            "lvhv_poweroff_channel",
            DEFAULT_LVHV_POWEROFF_CHANNEL,
        ),
        x728_soft_shutdown_line=get_int(
            "x728_soft_shutdown_line",
            DEFAULT_X728_SOFT_SHUTDOWN_LINE,
        ),
        x728_soft_shutdown_pulse_seconds=get_float(
            "x728_soft_shutdown_pulse_seconds",
            DEFAULT_X728_SOFT_SHUTDOWN_PULSE_SECONDS,
        ),
        x728_reboot_pulse_minimum_seconds=get_float(
            "x728_reboot_pulse_minimum_seconds",
            DEFAULT_X728_REBOOT_PULSE_MINIMUM_SECONDS,
        ),
        x728_shutdown_pulse_minimum_seconds=get_float(
            "x728_shutdown_pulse_minimum_seconds",
            DEFAULT_X728_SHUTDOWN_PULSE_MINIMUM_SECONDS,
        ),
        systemctl_path=Path(get_string("systemctl_path", DEFAULT_SYSTEMCTL_PATH)),
    )


def decode_state(
    signal_name: str,
    line_offset: int,
    raw_value: int,
    active_low: bool,
    source: str,
) -> AcPowerState:
    power_present = raw_value == 1 if active_low else raw_value == 0
    return AcPowerState(
        signal_name=signal_name,
        line_offset=line_offset,
        present=power_present,
        raw_value=raw_value,
        source=source,
        event_name="ac_power_restored" if power_present else "ac_power_lost",
        local_time=local_now_text(),
        utc_time=utc_now_text(),
    )


def log_event(state: AcPowerState) -> None:
    logging.info(
        "%s signal=%s gpio_line=%s raw_gpio=%s local_time=\"%s\" utc_time=\"%s\" source=%s",
        state.event_name,
        state.signal_name,
        state.line_offset,
        state.raw_value,
        state.local_time,
        state.utc_time,
        state.source,
    )


def state_to_dict(state: AcPowerState) -> dict:
    return {
        "ac_power_present": state.present,
        "raw_gpio": state.raw_value,
        "last_event": state.event_name,
        "last_event_local": state.local_time,
        "last_event_utc": state.utc_time,
        "source": state.source,
        "signal_name": state.signal_name,
        "gpio_line": state.line_offset,
    }


def update_state(state: AcPowerState) -> None:
    global current_state
    with state_lock:
        current_state = state
        input_states[state.signal_name] = state
        event_history.append(
            {
                "event": state.event_name,
                "signal_name": state.signal_name,
                "gpio_line": state.line_offset,
                "ac_power_present": state.present,
                "raw_gpio": state.raw_value,
                "local_time": state.local_time,
                "utc_time": state.utc_time,
                "source": state.source,
            }
        )


def swap_word_bytes(word: int) -> int:
    return ((word & 0xFF) << 8) | ((word >> 8) & 0xFF)


def read_battery_status() -> BatteryStatus:
    if smbus is None:
        return BatteryStatus(
            voltage_v=None,
            capacity_pct=None,
            source="i2c",
            error="python3-smbus is not installed",
        )

    try:
        bus = smbus.SMBus(DEFAULT_I2C_BUS)
        try:
            voltage_raw = swap_word_bytes(
                bus.read_word_data(DEFAULT_BATTERY_I2C_ADDRESS, 0x02)
            )
            capacity_raw = swap_word_bytes(
                bus.read_word_data(DEFAULT_BATTERY_I2C_ADDRESS, 0x04)
            )
        finally:
            bus.close()
    except OSError as exc:
        return BatteryStatus(
            voltage_v=None,
            capacity_pct=None,
            source="i2c",
            error=str(exc),
        )

    voltage_v = voltage_raw * 1.25 / 1000 / 16
    capacity_pct = capacity_raw / 256
    capacity_pct = max(0.0, min(100.0, capacity_pct))
    return BatteryStatus(
        voltage_v=round(voltage_v, 3),
        capacity_pct=round(capacity_pct, 2),
        source="i2c",
    )


def build_health_payload() -> dict:
    with state_lock:
        state = current_state
        history_size = len(event_history)
        states = dict(input_states)
    with soft_shutdown_lock:
        shutdown_state = dict(soft_shutdown_status)
    with x728_power_lock:
        power_state = dict(x728_power_status)
    battery = read_battery_status()
    payload = {
        "service": "pi-health-server",
        "started_at_utc": started_at_utc,
        "event_count_buffered": history_size,
        "battery_voltage_v": battery.voltage_v,
        "battery_capacity_pct": battery.capacity_pct,
        "battery_source": battery.source,
        "battery_error": battery.error,
        "soft_shutdown": shutdown_state,
        "x728_power": power_state,
        "ac_inputs": {
            name: {
                "gpio_line": signal_state.line_offset,
                "ac_power_present": signal_state.present,
                "raw_gpio": signal_state.raw_value,
                "last_event": signal_state.event_name,
                "last_event_local": signal_state.local_time,
                "last_event_utc": signal_state.utc_time,
                "source": signal_state.source,
            }
            for name, signal_state in states.items()
        },
    }
    if state is None:
        payload.update(
            {
                "ac_power_present": None,
                "raw_gpio": None,
                "last_event": None,
                "last_event_local": None,
                "last_event_utc": None,
                "source": None,
            }
        )
    else:
        payload.update(state_to_dict(state))
    return payload


def build_events_payload(limit: int) -> dict:
    with state_lock:
        events = list(event_history)[-limit:]
    return {
        "service": "pi-health-server",
        "events": events,
        "returned": len(events),
    }


def peer_is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def run_x728_soft_shutdown(config: PowerActionConfig) -> None:
    try:
        logging.warning(
            "requesting X728 soft shutdown command=%s",
            DEFAULT_X728_SHUTDOWN_COMMAND,
        )
        result = subprocess.run(
            [str(DEFAULT_X728_SHUTDOWN_COMMAND)],
            check=True,
            capture_output=True,
            text=True,
        )
        with soft_shutdown_lock:
            soft_shutdown_status.update(state="pulse_complete", error=None)
        logging.warning(
            "X728 soft shutdown command completed stdout=%s",
            result.stdout.strip(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        with soft_shutdown_lock:
            soft_shutdown_status.update(state="failed", error=str(exc))
        logging.exception("X728 soft shutdown failed: %s", exc)


def request_x728_soft_shutdown(config: PowerActionConfig) -> bool:
    with soft_shutdown_lock:
        if soft_shutdown_status["state"] == "pulsing":
            return False
        soft_shutdown_status.update(
            state="pulsing",
            requested_at_utc=utc_now_text(),
            error=None,
        )
    threading.Thread(
        target=run_x728_soft_shutdown,
        args=(config,),
        name="x728-soft-shutdown",
        # Keep the process alive long enough to restore the line LOW while
        # systemd is beginning the shutdown triggered by the X728.
        daemon=False,
    ).start()
    return True


def issue_system_action(action: str, config: PowerActionConfig) -> bool:
    with x728_power_lock:
        if x728_power_status["last_action"] in {"poweroff", "reboot"}:
            return False
        x728_power_status.update(
            state=f"{action}_requested",
            last_action=action,
            last_action_at_utc=utc_now_text(),
            error=None,
        )
    logging.warning("X728 requested system action=%s", action)
    try:
        subprocess.Popen(
            [str(config.systemctl_path), action],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        with x728_power_lock:
            x728_power_status.update(
                state="action_failed",
                last_action=None,
                error=str(exc),
            )
        logging.exception("failed to execute X728 system action=%s: %s", action, exc)
        return False
    return True


def handle_x728_power_edge(
    raw_value: int,
    config: PowerActionConfig,
    pulse_started_monotonic: float | None,
) -> float | None:
    now = time.monotonic()
    if raw_value == 1:
        if pulse_started_monotonic is None:
            with x728_power_lock:
                x728_power_status.update(
                    state="pulse_high",
                    pulse_started_at_utc=utc_now_text(),
                    error=None,
                )
            logging.info("X728 power signal HIGH gpio_line=%s", DEFAULT_X728_POWER_LINE)
            return now
        return pulse_started_monotonic

    if pulse_started_monotonic is None:
        return None

    duration = now - pulse_started_monotonic
    with x728_power_lock:
        x728_power_status.update(
            state="idle",
            last_pulse_seconds=round(duration, 3),
        )
    logging.info(
        "X728 power signal LOW gpio_line=%s pulse_seconds=%.3f",
        DEFAULT_X728_POWER_LINE,
        duration,
    )
    if duration > config.x728_shutdown_pulse_minimum_seconds:
        issue_system_action("poweroff", config)
    elif duration > config.x728_reboot_pulse_minimum_seconds:
        issue_system_action("reboot", config)
    return None


class PiHealthHandler(BaseHTTPRequestHandler):
    action_config = None

    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        if path == "/health":
            self.send_json(build_health_payload())
            return
        if path == "/events":
            limit = 100
            if query:
                for token in query.split("&"):
                    key, sep, value = token.partition("=")
                    if key == "limit" and sep:
                        try:
                            limit = max(1, min(int(value), DEFAULT_EVENT_BUFFER_SIZE))
                        except ValueError:
                            limit = 100
            self.send_json(build_events_payload(limit))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        path, _, _query = self.path.partition("?")
        if path != "/soft-shutdown":
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not peer_is_loopback(self.client_address[0]):
            self.send_error(
                HTTPStatus.FORBIDDEN,
                "soft shutdown is restricted to loopback clients; use the SSH tunnel",
            )
            return
        if self.action_config is None:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "action config unavailable")
            return
        accepted = request_x728_soft_shutdown(self.action_config)
        self.send_json(
            {
                "accepted": accepted,
                "message": (
                    "X728 soft shutdown pulse started"
                    if accepted
                    else "X728 soft shutdown is already in progress"
                ),
            },
            status=HTTPStatus.ACCEPTED if accepted else HTTPStatus.CONFLICT,
        )

    def log_message(self, format_str: str, *args) -> None:
        message = format_str % args
        if '"GET /health ' in message and message.endswith('" 200 -'):
            return
        logging.info("http %s - %s", self.address_string(), message)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def request_line(chip_path: str, line_offset: int):
    return request_lines(chip_path, [line_offset])


def request_lines(chip_path: str, line_offsets):
    chip = gpiod.Chip(chip_path)
    ac_line_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.PULL_UP,
    )
    x728_power_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
    )
    request = chip.request_lines(
        consumer=DEFAULT_CONSUMER,
        config={
            line_offset: (
                x728_power_settings
                if line_offset == DEFAULT_X728_POWER_LINE
                else ac_line_settings
            )
            for line_offset in line_offsets
        },
    )
    return chip, request


def read_line_value(request, line_offset: int) -> int:
    value = request.get_value(line_offset)
    if value is gpiod.line.Value.ACTIVE:
        return 1
    if value is gpiod.line.Value.INACTIVE:
        return 0
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)


def start_http_server(action_config: PowerActionConfig) -> ThreadingHTTPServer:
    PiHealthHandler.action_config = action_config
    server = ThreadingHTTPServer((DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT), PiHealthHandler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="pi-health-http",
        daemon=True,
    )
    thread.start()
    logging.info(
        "http server listening host=%s port=%s",
        DEFAULT_HTTP_HOST,
        DEFAULT_HTTP_PORT,
    )
    return server


def maybe_trigger_poweroff(state: AcPowerState, power_client: LvhvPowerOffClient) -> None:
    global gpio21_last_loss_monotonic

    if state.source == "startup" or state.present:
        return

    if state.signal_name == "gpio6_ac_status":
        try:
            power_client.power_off("gpio6 power lost")
        except OSError as exc:
            logging.exception("failed to issue gpio6-triggered powerOff: %s", exc)
        except RuntimeError as exc:
            logging.exception("failed to issue gpio6-triggered powerOff: %s", exc)
        return

    if state.signal_name != "gpio21_ac_fail":
        return

    window = power_client.config.gpio21_repeat_window_seconds
    now = time.monotonic()
    reason = None
    with power_action_lock:
        if (
            gpio21_last_loss_monotonic is not None
            and (now - gpio21_last_loss_monotonic) <= window
        ):
            gpio21_last_loss_monotonic = None
            reason = f"gpio21 repeated power loss within {window:.3f}s"
        else:
            gpio21_last_loss_monotonic = now
            logging.warning(
                "gpio21 power loss detected; waiting %.3fs for a repeated loss before powerOff",
                window,
            )

    if reason is None:
        return

    try:
        power_client.power_off(reason)
    except OSError as exc:
        logging.exception("failed to issue gpio21-triggered powerOff: %s", exc)
    except RuntimeError as exc:
        logging.exception("failed to issue gpio21-triggered powerOff: %s", exc)


def main() -> int:
    global started_at_utc
    global http_server

    configure_logging(DEFAULT_LOG_PATH)
    started_at_utc = utc_now_text()
    action_config = load_action_config(DEFAULT_ACTION_CONFIG_PATH)
    power_client = LvhvPowerOffClient(action_config)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logging.info(
        "starting GPIO monitor chip=%s gpio6_line=%s gpio6_active_low=%s gpio21_line=%s gpio21_active_low=%s x728_power_line=%s log_path=%s action_config=%s lvhv_host=%s lvhv_port=%s gpio21_repeat_window_seconds=%s",
        DEFAULT_GPIO_CHIP,
        DEFAULT_GPIO6_LINE,
        DEFAULT_GPIO6_ACTIVE_LOW,
        DEFAULT_GPIO21_LINE,
        DEFAULT_GPIO21_ACTIVE_LOW,
        DEFAULT_X728_POWER_LINE,
        DEFAULT_LOG_PATH,
        DEFAULT_ACTION_CONFIG_PATH,
        action_config.lvhv_host,
        action_config.lvhv_port,
        action_config.gpio21_repeat_window_seconds,
    )

    http_server = start_http_server(action_config)
    signal_configs = {
        "gpio6_ac_status": {
            "line_offset": DEFAULT_GPIO6_LINE,
            "active_low": DEFAULT_GPIO6_ACTIVE_LOW,
        },
        "gpio21_ac_fail": {
            "line_offset": DEFAULT_GPIO21_LINE,
            "active_low": DEFAULT_GPIO21_ACTIVE_LOW,
        },
    }
    chip, request = request_lines(
        DEFAULT_GPIO_CHIP,
        [config["line_offset"] for config in signal_configs.values()]
        + [DEFAULT_X728_POWER_LINE],
    )
    x728_pulse_started = None
    try:
        for signal_name, config in signal_configs.items():
            initial_value = read_line_value(request, config["line_offset"])
            initial_state = decode_state(
                signal_name,
                config["line_offset"],
                initial_value,
                config["active_low"],
                "startup",
            )
            update_state(initial_state)
            log_event(initial_state)

        initial_x728_value = read_line_value(request, DEFAULT_X728_POWER_LINE)
        if initial_x728_value == 1:
            x728_pulse_started = handle_x728_power_edge(
                initial_x728_value,
                action_config,
                None,
            )

        while running:
            if (
                x728_pulse_started is not None
                and time.monotonic() - x728_pulse_started
                > action_config.x728_shutdown_pulse_minimum_seconds
            ):
                issue_system_action("poweroff", action_config)

            if not request.wait_edge_events(
                timeout=0.05 if x728_pulse_started is not None else 1.0
            ):
                continue

            for event in request.read_edge_events():
                line_offset = event.line_offset
                value = read_line_value(request, line_offset)
                if line_offset == DEFAULT_X728_POWER_LINE:
                    x728_pulse_started = handle_x728_power_edge(
                        value,
                        action_config,
                        x728_pulse_started,
                    )
                    continue
                signal_name = next(
                    name
                    for name, config in signal_configs.items()
                    if config["line_offset"] == line_offset
                )
                source = (
                    "edge_rising"
                    if event.event_type is gpiod.EdgeEvent.Type.RISING_EDGE
                    else "edge_falling"
                )
                state = decode_state(
                    signal_name,
                    line_offset,
                    value,
                    signal_configs[signal_name]["active_low"],
                    source,
                )
                update_state(state)
                log_event(state)
                maybe_trigger_poweroff(state, power_client)
    finally:
        if http_server is not None:
            http_server.shutdown()
            http_server.server_close()
        request.release()
        chip.close()
        logging.info("GPIO monitor stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
