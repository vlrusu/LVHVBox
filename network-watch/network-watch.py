#!/usr/bin/env python3
"""Watch fleet network reachability and locally shut off LV on isolation."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import struct
import sys
import time
from pathlib import Path


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
DEFAULT_CONNECT_TIMEOUT_S = float(os.getenv("NETWORK_WATCH_CONNECT_TIMEOUT_S", "3.0"))
DEFAULT_FAILURE_STREAK_TRIGGER = int(os.getenv("NETWORK_WATCH_FAILURE_STREAK_TRIGGER", "3"))
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

    def power_off(self, reason: str) -> None:
        message = self._encode_message()
        with socket.create_connection((DEFAULT_LVHV_HOST, DEFAULT_LVHV_PORT), timeout=5.0) as connection:
            connection.settimeout(5.0)
            connection.sendall(message)
            self._read_reply(connection)
        logging.warning(
            "issued local powerOff to lvhv-server host=%s port=%s channel=%s reason=%s",
            DEFAULT_LVHV_HOST,
            DEFAULT_LVHV_PORT,
            DEFAULT_LVHV_POWEROFF_CHANNEL,
            reason,
        )


def build_master_hosts() -> list[str]:
    return list(DEFAULT_MASTER_HOSTS)


def probe_host(host: str) -> tuple[bool, str | None]:
    try:
        with socket.create_connection(
            (host, DEFAULT_REMOTE_PORT),
            timeout=DEFAULT_CONNECT_TIMEOUT_S,
        ):
            return True, None
    except Exception as exc:
        return False, repr(exc)


def main() -> int:
    global failure_streak, shutdown_latched, runtime_args

    runtime_args = parse_args()

    configure_logging(DEFAULT_LOG_PATH)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    power_client = LocalPowerOffClient(DEFAULT_LVHV_COMMANDS_PATH)
    master_hosts = build_master_hosts()
    if not DEFAULT_MASTER_HOSTS:
        raise SystemExit("no master hosts configured; set NETWORK_WATCH_MASTER_HOSTS")

    logging.info(
        "starting network-watch local_host=%s masters=%s remote_port=%s policy=all trigger_streak=%s dry_run=%s",
        DEFAULT_LOCAL_HOSTNAME,
        ",".join(master_hosts),
        DEFAULT_REMOTE_PORT,
        DEFAULT_FAILURE_STREAK_TRIGGER,
        runtime_args.dry_run,
    )

    while running:
        reachable = []
        failed = []
        for host in master_hosts:
            ok, error = probe_host(host)
            if ok:
                reachable.append(host)
            else:
                failed.append((host, error or "unknown"))

        if len(reachable) == len(master_hosts):
            if shutdown_latched:
                logging.info(
                    "master connectivity restored reachable=%s failed=%s; clearing network shutdown latch",
                    len(reachable),
                    len(failed),
                )
            failure_streak = 0
            shutdown_latched = False
        else:
            failure_streak += 1
            logging.error(
                "master connectivity degraded streak=%s/%s reachable=%s required=%s failed=%s",
                failure_streak,
                DEFAULT_FAILURE_STREAK_TRIGGER,
                len(reachable),
                len(master_hosts),
                ", ".join(f"{host}: {error}" for host, error in failed),
            )
            if failure_streak >= DEFAULT_FAILURE_STREAK_TRIGGER:
                reason = (
                    f"master isolation reachable={len(reachable)} "
                    f"required={len(master_hosts)} streak={failure_streak}"
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
