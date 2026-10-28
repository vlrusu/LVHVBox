#!/usr/bin/env python3
"""Watch fleet network reachability and locally shut off LV on isolation."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import lvhv_protocol as protocol
except ModuleNotFoundError as error:
    if error.name != 'lvhv_protocol':
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
    import lvhv_protocol as protocol


DEFAULT_LOG_PATH = Path(
    os.getenv(
        "NETWORK_WATCH_LOG_PATH",
        "/var/log/mu2e-tracker-network-watch/network-watch.log",
    )
)
DEFAULT_PERIOD_S = float(os.getenv("NETWORK_WATCH_PERIOD_S", "30.0"))
DEFAULT_LOCAL_HOSTNAME = os.getenv("NETWORK_WATCH_LOCAL_HOSTNAME") or socket.gethostname()
DEFAULT_MASTER_HOSTS = [
    host.strip()
    for host in os.getenv("NETWORK_WATCH_MASTER_HOSTS", "").split(",")
    if host.strip()
]
DEFAULT_REMOTE_PORT = int(os.getenv("NETWORK_WATCH_REMOTE_PORT", "12000"))
DEFAULT_MASTER_ENDPOINTS_RAW = os.getenv("NETWORK_WATCH_MASTER_ENDPOINTS", "").strip()
DEFAULT_GATEWAY_ENDPOINTS_RAW = os.getenv("NETWORK_WATCH_GATEWAY_ENDPOINTS", "").strip()
DEFAULT_CONNECT_TIMEOUT_S = float(os.getenv("NETWORK_WATCH_CONNECT_TIMEOUT_S", "3.0"))
DEFAULT_GRACE_PERIOD_S = float(os.getenv("NETWORK_WATCH_GRACE_PERIOD_S", "1800.0"))
DEFAULT_LVHV_HOST = os.getenv("NETWORK_WATCH_LVHV_HOST", "127.0.0.1")
DEFAULT_LVHV_PORT = int(os.getenv("NETWORK_WATCH_LVHV_PORT", "12000"))
DEFAULT_LVHV_COMMANDS_PATH = Path(
    os.getenv("NETWORK_WATCH_LVHV_COMMANDS_PATH", "/etc/mu2e-tracker-lvhv-tools/commands.h")
)
DEFAULT_LVHV_POWEROFF_CHANNEL = int(os.getenv("NETWORK_WATCH_LVHV_POWEROFF_CHANNEL", "6"))

running = True
failure_streak = 0
shutdown_latched = False
runtime_args = None


@dataclass(frozen=True)
class ProbeEndpoint:
    host: str
    port: int

    @property
    def label(self) -> str:
        return f"{self.host}:{self.port}"


def handle_signal(signum: int, _frame) -> None:
    global running
    running = False
    logging.info("received signal %s, shutting down", signum)


def parse_args():
    parser = argparse.ArgumentParser(description="PSU master reachability watcher")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate isolation and log intended local powerOff actions without sending them",
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


class LocalPowerOffClient:
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

    def _encode_message(self) -> bytes:
        return protocol.encode_request(self.command_codes['COMMAND_powerOff'],
            self.command_codes['TYPE_lv'], DEFAULT_LVHV_POWEROFF_CHANNEL)

    def power_off(self, reason: str) -> None:
        with socket.create_connection((DEFAULT_LVHV_HOST, DEFAULT_LVHV_PORT), timeout=5.0) as connection:
            reply = protocol.request_reply(connection, self.command_codes['COMMAND_powerOff'],
                self.command_codes['TYPE_lv'], DEFAULT_LVHV_POWEROFF_CHANNEL, timeout=5.0)
            protocol.require_success(reply)
        logging.warning(
            "issued local powerOff to lvhv-server host=%s port=%s channel=%s reason=%s",
            DEFAULT_LVHV_HOST,
            DEFAULT_LVHV_PORT,
            DEFAULT_LVHV_POWEROFF_CHANNEL,
            reason,
        )


def parse_endpoint(raw_endpoint: str) -> ProbeEndpoint:
    endpoint = raw_endpoint.strip()
    if not endpoint:
        raise ValueError("empty endpoint")
    if ":" not in endpoint:
        return ProbeEndpoint(endpoint, DEFAULT_REMOTE_PORT)
    host, port_text = endpoint.rsplit(":", 1)
    host = host.strip()
    port_text = port_text.strip()
    if not host or not port_text:
        raise ValueError(f"invalid endpoint {raw_endpoint!r}; expected host:port")
    try:
        port = int(port_text, 10)
    except ValueError as exc:
        raise ValueError(f"invalid endpoint port in {raw_endpoint!r}") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"invalid endpoint port in {raw_endpoint!r}; expected 1-65535")
    return ProbeEndpoint(host, port)


def build_master_endpoints() -> list[ProbeEndpoint]:
    if DEFAULT_MASTER_ENDPOINTS_RAW:
        return [
            parse_endpoint(endpoint)
            for endpoint in DEFAULT_MASTER_ENDPOINTS_RAW.split(",")
            if endpoint.strip()
        ]
    return [ProbeEndpoint(host, DEFAULT_REMOTE_PORT) for host in DEFAULT_MASTER_HOSTS]


def probe_endpoint(endpoint: ProbeEndpoint) -> tuple[bool, str | None]:
    try:
        with socket.create_connection(
            (endpoint.host, endpoint.port),
            timeout=DEFAULT_CONNECT_TIMEOUT_S,
        ):
            return True, None
    except Exception as exc:
        return False, repr(exc)


def main() -> int:
    global failure_streak, shutdown_latched, runtime_args

    runtime_args = parse_args()

    if not 0 < DEFAULT_GRACE_PERIOD_S < float("inf"):
        raise SystemExit("NETWORK_WATCH_GRACE_PERIOD_S must be positive and finite")
    outage_started = None

    configure_logging(DEFAULT_LOG_PATH)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    power_client = LocalPowerOffClient(DEFAULT_LVHV_COMMANDS_PATH)
    try:
        master_endpoints = build_master_endpoints()
        gateway_endpoints = [
            parse_endpoint(endpoint)
            for endpoint in DEFAULT_GATEWAY_ENDPOINTS_RAW.split(",")
            if endpoint.strip()
        ]
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not master_endpoints:
        raise SystemExit(
            "no master endpoints configured; set NETWORK_WATCH_MASTER_ENDPOINTS "
            "or NETWORK_WATCH_MASTER_HOSTS"
        )

    probe_groups = [[endpoint] for endpoint in master_endpoints]
    if gateway_endpoints:
        probe_groups.append(gateway_endpoints)

    logging.info(
        "starting network-watch local_host=%s endpoints=%s policy=all_groups_any_endpoint grace_period_s=%s dry_run=%s",
        DEFAULT_LOCAL_HOSTNAME,
        ",".join("|".join(endpoint.label for endpoint in group) for group in probe_groups),
        DEFAULT_GRACE_PERIOD_S,
        runtime_args.dry_run,
    )

    while running:
        reachable = []
        failed = []
        for group in probe_groups:
            group_failures = []
            for endpoint in group:
                ok, error = probe_endpoint(endpoint)
                if ok:
                    reachable.append(endpoint)
                    if group_failures:
                        logging.info(
                            "master endpoint fallback reachable=%s failed=%s",
                            endpoint.label,
                            ", ".join(f"{ep.label}: {err}" for ep, err in group_failures),
                        )
                    break
                group_failures.append((endpoint, error or "unknown"))
            else:
                failed.extend(group_failures)

        if len(reachable) == len(probe_groups):
            if shutdown_latched:
                logging.info(
                    "master connectivity restored reachable=%s failed=%s; clearing network shutdown latch",
                    len(reachable),
                    len(failed),
                )
            failure_streak = 0
            shutdown_latched = False
            outage_started = None
        else:
            failure_streak += 1
            now = time.monotonic()
            if outage_started is None:
                outage_started = now
            outage_elapsed = now - outage_started
            logging.error(
                "master connectivity degraded streak=%s outage_elapsed_s=%.1f grace_period_s=%s reachable=%s required=%s failed=%s",
                failure_streak,
                outage_elapsed,
                DEFAULT_GRACE_PERIOD_S,
                len(reachable),
                len(probe_groups),
                ", ".join(f"{endpoint.label}: {error}" for endpoint, error in failed),
            )
            if outage_elapsed >= DEFAULT_GRACE_PERIOD_S:
                reason = (
                    f"master isolation reachable={len(reachable)} "
                    f"required={len(probe_groups)} streak={failure_streak} "
                    f"outage_elapsed_s={outage_elapsed:.1f} grace_period_s={DEFAULT_GRACE_PERIOD_S}"
                )
                if runtime_args.dry_run:
                    logging.warning("dry-run: would issue local powerOff reason=%s", reason)
                else:
                    power_client.power_off(reason)
                if not shutdown_latched:
                    logging.warning("set network shutdown latch")
                shutdown_latched = True

        time.sleep(DEFAULT_PERIOD_S)

    logging.info("network-watch stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
