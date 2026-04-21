#!/usr/bin/env python3
"""Monitor Raspberry Pi health GPIOs and log AC power events."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
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
DEFAULT_GPIO_LINE = int(os.getenv("PI_HEALTH_AC_GPIO_LINE", "6"))
DEFAULT_ACTIVE_LOW = os.getenv("PI_HEALTH_GPIO_ACTIVE_LOW", "0").lower() not in {
    "0",
    "false",
    "no",
}
DEFAULT_LOG_PATH = Path(
    os.getenv("PI_HEALTH_LOG_PATH", "/var/log/pi-health/ac-power-events.log")
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


running = True
state_lock = threading.Lock()
event_history = deque(maxlen=DEFAULT_EVENT_BUFFER_SIZE)
current_state = None
started_at_utc = None
http_server = None


def handle_signal(signum: int, _frame) -> None:
    global running
    running = False
    logging.info("received signal %s, shutting down", signum)


@dataclass(frozen=True)
class AcPowerState:
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


def decode_state(raw_value: int, active_low: bool, source: str) -> AcPowerState:
    power_present = raw_value == 1 if active_low else raw_value == 0
    return AcPowerState(
        present=power_present,
        raw_value=raw_value,
        source=source,
        event_name="ac_power_restored" if power_present else "ac_power_lost",
        local_time=local_now_text(),
        utc_time=utc_now_text(),
    )


def log_event(state: AcPowerState) -> None:
    logging.info(
        "%s raw_gpio=%s local_time=\"%s\" utc_time=\"%s\" source=%s",
        state.event_name,
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
    }


def update_state(state: AcPowerState) -> None:
    global current_state
    with state_lock:
        current_state = state
        event_history.append(
            {
                "event": state.event_name,
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
    battery = read_battery_status()
    payload = {
        "service": "pi-health-server",
        "started_at_utc": started_at_utc,
        "event_count_buffered": history_size,
        "battery_voltage_v": battery.voltage_v,
        "battery_capacity_pct": battery.capacity_pct,
        "battery_source": battery.source,
        "battery_error": battery.error,
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


class PiHealthHandler(BaseHTTPRequestHandler):
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

    def log_message(self, format_str: str, *args) -> None:
        logging.info("http %s - %s", self.address_string(), format_str % args)

    def send_json(self, payload: dict) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def request_line(chip_path: str, line_offset: int):
    chip = gpiod.Chip(chip_path)
    line_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.PULL_UP,
    )
    request = chip.request_lines(
        consumer=DEFAULT_CONSUMER,
        config={line_offset: line_settings},
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


def start_http_server() -> ThreadingHTTPServer:
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


def main() -> int:
    global started_at_utc
    global http_server

    configure_logging(DEFAULT_LOG_PATH)
    started_at_utc = utc_now_text()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logging.info(
        "starting GPIO monitor chip=%s line=%s active_low=%s log_path=%s",
        DEFAULT_GPIO_CHIP,
        DEFAULT_GPIO_LINE,
        DEFAULT_ACTIVE_LOW,
        DEFAULT_LOG_PATH,
    )

    http_server = start_http_server()
    chip, request = request_line(DEFAULT_GPIO_CHIP, DEFAULT_GPIO_LINE)
    try:
        initial_value = read_line_value(request, DEFAULT_GPIO_LINE)
        initial_state = decode_state(initial_value, DEFAULT_ACTIVE_LOW, "startup")
        update_state(initial_state)
        log_event(initial_state)

        while running:
            if not request.wait_edge_events(timeout=1.0):
                continue

            for event in request.read_edge_events():
                value = read_line_value(request, DEFAULT_GPIO_LINE)
                source = (
                    "edge_rising"
                    if event.event_type is gpiod.EdgeEvent.Type.RISING_EDGE
                    else "edge_falling"
                )
                state = decode_state(value, DEFAULT_ACTIVE_LOW, source)
                update_state(state)
                log_event(state)
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
