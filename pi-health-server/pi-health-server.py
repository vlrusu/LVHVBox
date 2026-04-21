#!/usr/bin/env python3
"""Monitor Raspberry Pi health GPIOs and log AC power events."""

from __future__ import annotations

import logging
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import gpiod
    from gpiod.line import Bias, Direction, Edge
except ImportError as exc:  # pragma: no cover - import failure is runtime-specific
    raise SystemExit(
        "python3-gpiod is required. Install it with: sudo apt-get install -y python3-gpiod"
    ) from exc


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


running = True


def handle_signal(signum: int, _frame) -> None:
    global running
    running = False
    logging.info("received signal %s, shutting down", signum)


@dataclass(frozen=True)
class AcPowerState:
    present: bool
    raw_value: int
    source: str


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
    return AcPowerState(present=power_present, raw_value=raw_value, source=source)


def log_event(state: AcPowerState) -> None:
    event_name = "ac_power_restored" if state.present else "ac_power_lost"
    logging.info(
        "%s raw_gpio=%s local_time=\"%s\" utc_time=\"%s\" source=%s",
        event_name,
        state.raw_value,
        local_now_text(),
        utc_now_text(),
        state.source,
    )


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
    return int(request.get_value(line_offset))


def main() -> int:
    configure_logging(DEFAULT_LOG_PATH)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logging.info(
        "starting GPIO monitor chip=%s line=%s active_low=%s log_path=%s",
        DEFAULT_GPIO_CHIP,
        DEFAULT_GPIO_LINE,
        DEFAULT_ACTIVE_LOW,
        DEFAULT_LOG_PATH,
    )

    chip, request = request_line(DEFAULT_GPIO_CHIP, DEFAULT_GPIO_LINE)
    try:
        initial_value = read_line_value(request, DEFAULT_GPIO_LINE)
        log_event(decode_state(initial_value, DEFAULT_ACTIVE_LOW, "startup"))

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
                log_event(decode_state(value, DEFAULT_ACTIVE_LOW, source))
    finally:
        request.release()
        chip.close()
        logging.info("GPIO monitor stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
