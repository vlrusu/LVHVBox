#!/usr/bin/env python3

import argparse
import csv
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib.pyplot as plt

from PowerSupplyServerConnection import PowerSupplyServerConnection


DEFAULT_GATEWAY = "mu2egateway01.fnal.gov"
DEFAULT_REMOTE_PORT = 12000
DEFAULT_USER = "mu2e"
DEFAULT_START = 0
DEFAULT_STOP = 17


def normalize_host(hostname):
    if hostname in ("localhost", "127.0.0.1"):
        return hostname
    if "." in hostname:
        return hostname
    return f"mu2e-trk-{hostname}.fnal.gov"


def local_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class SshTunnel:
    def __init__(self, host, user, gateway, remote_port, use_ssh_config):
        self.host = host
        self.user = user
        self.gateway = gateway
        self.remote_port = remote_port
        self.use_ssh_config = use_ssh_config
        self.local_port = find_free_port()
        self.process = None

    def __enter__(self):
        ssh_cmd = ["ssh", "-N", "-K", "-X", "-o", "ExitOnForwardFailure=yes"]
        if not self.use_ssh_config:
            ssh_cmd.extend(["-J", self.gateway])
        ssh_cmd.extend(["-L", f"{self.local_port}:localhost:{self.remote_port}"])
        if self.use_ssh_config:
            ssh_cmd.append(self.host)
        else:
            ssh_cmd.append(f"{self.user}@{self.host}")
        self.process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(30):
            if self.process.poll() is not None:
                stderr = ""
                if self.process.stderr is not None:
                    stderr = self.process.stderr.read().strip()
                message = stderr or "SSH tunnel exited before becoming ready"
                raise RuntimeError(message)
            if local_port_open(self.local_port):
                return self.local_port
            time.sleep(0.2)
        self.__exit__(None, None, None)
        raise RuntimeError("SSH tunnel did not become ready")

    def __exit__(self, exc_type, exc, tb):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)


def query_one_psu(host, user, gateway, remote_port, header, use_ssh_config):
    target_host = host if use_ssh_config else normalize_host(host)
    if target_host in ("localhost", "127.0.0.1"):
        connection_host = target_host
        connection_port = remote_port
        tunnel = None
    else:
        tunnel = SshTunnel(target_host, user, gateway, remote_port, use_ssh_config)
        connection_port = tunnel.__enter__()
        connection_host = "127.0.0.1"

    supply = None
    try:
        supply = PowerSupplyServerConnection(connection_host, connection_port, header)
        voltages = list(supply.QueryPowerVoltages())
        if len(voltages) != 6:
            raise RuntimeError(f"Expected 6 channels, got {len(voltages)}")
        return voltages
    finally:
        if supply is not None:
            try:
                supply.close()
            except OSError:
                pass
        if tunnel is not None:
            tunnel.__exit__(None, None, None)


def write_csv(rows, output_path):
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["host", "channel", "v48"])
        writer.writerows(rows)


def plot_histogram(values, output_path, title):
    plt.figure(figsize=(10, 6))
    plt.hist(values, bins="auto", edgecolor="black")
    plt.xlabel("V48 [V]")
    plt.ylabel("Count")
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)


def parse_args():
    default_header = Path(__file__).resolve().parent.parent / "commands.h"
    parser = argparse.ArgumentParser(
        description="Read V48 for all channels on mu2e-trk-psu0..17 and make a histogram."
    )
    parser.add_argument("--start", type=int, default=DEFAULT_START, help="First PSU index")
    parser.add_argument("--stop", type=int, default=DEFAULT_STOP, help="Last PSU index, inclusive")
    parser.add_argument("--user", default=DEFAULT_USER, help="SSH username")
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY, help="SSH jump host")
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT, help="Remote LV/HV server port")
    parser.add_argument("--header", default=str(default_header), help="Local path to commands.h")
    parser.add_argument("--workers", type=int, default=6, help="Parallel PSU queries")
    parser.add_argument("--csv-out", default="v48_all_pis.csv", help="Output CSV path")
    parser.add_argument("--plot-out", default="v48_all_pis_hist.png", help="Output histogram image path")
    parser.add_argument(
        "--ssh-mode",
        choices=("config", "explicit"),
        default="config",
        help="Use SSH host aliases from ~/.ssh/config or explicit user/gateway settings",
    )
    parser.add_argument(
        "--host-prefix",
        default="psu",
        help="Host prefix to use in config mode, e.g. psu -> psu0..psu17",
    )
    parser.add_argument("--show", action="store_true", help="Display the histogram window")
    return parser.parse_args()


def main():
    args = parse_args()
    use_ssh_config = args.ssh_mode == "config"
    if use_ssh_config:
        hosts = [f"{args.host_prefix}{i}" for i in range(args.start, args.stop + 1)]
    else:
        hosts = [f"mu2e-trk-psu{i}" for i in range(args.start, args.stop + 1)]
    header = str(Path(args.header).resolve())

    results = {}
    failures = {}
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(
                query_one_psu,
                host,
                args.user,
                args.gateway,
                args.remote_port,
                header,
                use_ssh_config,
            ): host
            for host in hosts
        }
        for future in as_completed(future_map):
            host = future_map[future]
            try:
                voltages = future.result()
                with lock:
                    results[host] = voltages
                print(f"{host}: " + ", ".join(f"ch{ch}={value:.3f} V" for ch, value in enumerate(voltages)))
            except Exception as exc:
                with lock:
                    failures[host] = str(exc)
                print(f"{host}: FAILED ({exc})")

    rows = []
    values = []
    for host in sorted(results, key=lambda name: int(name.rsplit("psu", 1)[1])):
        for channel, value in enumerate(results[host]):
            rows.append([host, channel, value])
            values.append(value)

    if not values:
        raise RuntimeError("No V48 values were collected")

    csv_out = Path(args.csv_out).resolve()
    plot_out = Path(args.plot_out).resolve()
    write_csv(rows, csv_out)
    plot_histogram(values, plot_out, f"V48 Histogram for {len(rows)} Channels Across {len(results)} PSUs")

    print(f"\nCollected {len(values)} values from {len(results)} PSUs")
    print(f"CSV: {csv_out}")
    print(f"Plot: {plot_out}")
    if failures:
        print("\nFailures:")
        for host in sorted(failures, key=lambda name: int(name.rsplit("psu", 1)[1])):
            print(f"  {host}: {failures[host]}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
