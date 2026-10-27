#!/usr/bin/env python3

import argparse
import csv
import datetime
import sqlite3
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from PowerSupplyServerConnection import PowerSupplyServerConnection


DEFAULT_GATEWAY = "mu2egateway01.fnal.gov"
DEFAULT_REMOTE_PORT = 12000
DEFAULT_USER = "mu2e"
DEFAULT_START = 0
DEFAULT_STOP = 17
DEFAULT_EXCLUDE = []
DEFAULT_CSV_BASENAME = "v6_all_pis.csv"
DEFAULT_DB_BASENAME = "v6_all_pis.db"
LV_CHANNELS = 6


def now():
    return datetime.datetime.now()


def default_csv_path():
    timestamp = now().strftime("%Y%m%d_%H%M%S")
    return f"v6_all_pis_{timestamp}.csv"


def default_db_path():
    timestamp = now().strftime("%Y%m%d_%H%M%S")
    return f"v6_all_pis_{timestamp}.db"


def normalize_host(hostname):
    if hostname in ("localhost", "127.0.0.1"):
        return hostname
    if "." in hostname:
        return hostname
    if hostname.startswith("mu2e-trk-"):
        return f"{hostname}.fnal.gov"
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
    def __init__(self, host, user, gateway, remote_port, ssh_mode):
        self.host = host
        self.user = user
        self.gateway = gateway
        self.remote_port = remote_port
        self.ssh_mode = ssh_mode
        self.local_port = find_free_port()
        self.process = None

    def __enter__(self):
        ssh_cmd = ["ssh", "-N", "-K", "-X", "-o", "ExitOnForwardFailure=yes"]
        if self.ssh_mode == "explicit":
            ssh_cmd.extend(["-J", self.gateway])
        ssh_cmd.extend(["-L", f"{self.local_port}:localhost:{self.remote_port}"])
        if self.ssh_mode == "config":
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


class PersistentPsuConnection:
    def __init__(self, host, user, gateway, remote_port, header, ssh_mode):
        self.host = host
        self.user = user
        self.gateway = gateway
        self.remote_port = remote_port
        self.header = header
        self.ssh_mode = ssh_mode
        self.tunnel = None
        self.supply = None

    def connect(self):
        target_host = self.host if self.ssh_mode == "config" else normalize_host(self.host)
        if target_host in ("localhost", "127.0.0.1"):
            connection_host = target_host
            connection_port = self.remote_port
        else:
            self.tunnel = SshTunnel(
                target_host,
                self.user,
                self.gateway,
                self.remote_port,
                self.ssh_mode,
            )
            connection_port = self.tunnel.__enter__()
            connection_host = "127.0.0.1"
        self.supply = PowerSupplyServerConnection(connection_host, connection_port, self.header)
        return self

    def query_v6(self):
        if self.supply is None:
            raise RuntimeError("PSU connection is not open")
        voltages = list(self.supply.QuerySwitchingVoltages())
        if len(voltages) != LV_CHANNELS:
            raise RuntimeError(f"Expected {LV_CHANNELS} channels, got {len(voltages)}")
        return voltages

    def query_i6(self):
        if self.supply is None:
            raise RuntimeError("PSU connection is not open")
        currents = list(self.supply.QuerySwitchingCurrents())
        if len(currents) != LV_CHANNELS:
            raise RuntimeError(f"Expected {LV_CHANNELS} channels, got {len(currents)}")
        return currents

    def query_v48(self):
        if self.supply is None:
            raise RuntimeError("PSU connection is not open")
        voltages = list(self.supply.QueryPowerVoltages())
        if len(voltages) != LV_CHANNELS:
            raise RuntimeError(f"Expected {LV_CHANNELS} channels, got {len(voltages)}")
        return voltages

    def query_i48(self):
        if self.supply is None:
            raise RuntimeError("PSU connection is not open")
        currents = list(self.supply.QueryPowerCurrents())
        if len(currents) != LV_CHANNELS:
            raise RuntimeError(f"Expected {LV_CHANNELS} channels, got {len(currents)}")
        return currents

    def close(self):
        if self.supply is not None:
            try:
                self.supply.close()
            except OSError:
                pass
            self.supply = None
        if self.tunnel is not None:
            self.tunnel.__exit__(None, None, None)
            self.tunnel = None


def query_one_psu(host, user, gateway, remote_port, header, ssh_mode):
    connection = None
    try:
        connection = PersistentPsuConnection(
            host,
            user,
            gateway,
            remote_port,
            header,
            ssh_mode,
        ).connect()
        return {
            "v6": connection.query_v6(),
            "i6": connection.query_i6(),
            "v48": connection.query_v48(),
            "i48": connection.query_i48(),
        }
    finally:
        if connection is not None:
            connection.close()


def write_csv(rows, output_path):
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["host", "box", "channel", "v6", "i6", "v48", "i48"])
        writer.writerows(rows)


def write_sqlite(rows, output_path):
    connection = sqlite3.connect(output_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                host TEXT NOT NULL,
                box INTEGER NOT NULL,
                channel INTEGER NOT NULL,
                v6 REAL,
                i6 REAL,
                v48 REAL,
                i48 REAL
            )
            """
        )
        cursor.execute("DELETE FROM measurements")
        cursor.executemany(
            """
            INSERT INTO measurements (host, box, channel, v6, i6, v48, i48)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def make_live_csv_logger(output_path, hosts):
    handle = output_path.open("w", newline="")
    writer = csv.writer(handle)
    header = ["timestamp"]
    for host in hosts:
        for channel in range(LV_CHANNELS):
            header.append(f"{host}_ch{channel}_v6")
    for host in hosts:
        for channel in range(LV_CHANNELS):
            header.append(f"{host}_ch{channel}_i6")
    for host in hosts:
        for channel in range(LV_CHANNELS):
            header.append(f"{host}_ch{channel}_v48")
    for host in hosts:
        for channel in range(LV_CHANNELS):
            header.append(f"{host}_ch{channel}_i48")
    writer.writerow(header)
    handle.flush()

    def logger(timestamp, results):
        row = [timestamp.isoformat()]
        for host in hosts:
            values = results.get(host)
            for channel in range(LV_CHANNELS):
                if values is None:
                    row.append("")
                else:
                    row.append(values["v6"][channel])
        for host in hosts:
            values = results.get(host)
            for channel in range(LV_CHANNELS):
                if values is None:
                    row.append("")
                else:
                    row.append(values["i6"][channel])
        for host in hosts:
            values = results.get(host)
            for channel in range(LV_CHANNELS):
                if values is None:
                    row.append("")
                else:
                    row.append(values["v48"][channel])
        for host in hosts:
            values = results.get(host)
            for channel in range(LV_CHANNELS):
                if values is None:
                    row.append("")
                else:
                    row.append(values["i48"][channel])
        writer.writerow(row)
        handle.flush()

    return handle, logger


def make_live_sqlite_logger(output_path):
    connection = sqlite3.connect(output_path)
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS measurements (
            timestamp TEXT NOT NULL,
            host TEXT NOT NULL,
            channel INTEGER NOT NULL,
            v6 REAL,
            i6 REAL,
            v48 REAL,
            i48 REAL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_measurements_time ON measurements(timestamp)"
    )
    connection.commit()

    def logger(timestamp, results):
        rows = []
        for host, values in results.items():
            for channel in range(LV_CHANNELS):
                rows.append(
                    (
                        timestamp.isoformat(),
                        host,
                        channel,
                        values["v6"][channel],
                        values["i6"][channel],
                        values["v48"][channel],
                        values["i48"][channel],
                    )
                )
        cursor.executemany(
            """
            INSERT INTO measurements (timestamp, host, channel, v6, i6, v48, i48)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()

    return connection, logger


def make_data_logger(args, ordered_hosts):
    if args.sqlite:
        db_out = Path(args.db_out).resolve()
        return db_out, make_live_sqlite_logger(db_out)
    csv_out = Path(args.csv_out).resolve()
    return csv_out, make_live_csv_logger(csv_out, ordered_hosts)


def collect_v6(hosts, user, gateway, remote_port, header, ssh_mode, workers):
    results = {}
    failures = {}
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                query_one_psu,
                host,
                user,
                gateway,
                remote_port,
                header,
                ssh_mode,
            ): host
            for host in hosts
        }
        for future in as_completed(future_map):
            host = future_map[future]
            try:
                measurements = future.result()
                with lock:
                    results[host] = measurements
            except Exception as exc:
                with lock:
                    failures[host] = str(exc)

    return results, failures


def rows_from_results(results):
    ordered_hosts = sorted(results, key=lambda name: int(name.rsplit("psu", 1)[1]))
    rows = []
    for box_index, host in enumerate(ordered_hosts):
        for channel in range(LV_CHANNELS):
            rows.append([
                host,
                box_index,
                channel,
                results[host]["v6"][channel],
                results[host]["i6"][channel],
                results[host]["v48"][channel],
                results[host]["i48"][channel],
            ])
    return rows


def plot_v6(results, output_path, title):
    ordered_hosts = sorted(results, key=lambda name: int(name.rsplit("psu", 1)[1]))
    x_positions = list(range(len(ordered_hosts)))

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    ax_v6, ax_i6 = axes[0]
    ax_v48, ax_i48 = axes[1]
    for channel in range(LV_CHANNELS):
        y_v6 = [results[host]["v6"][channel] for host in ordered_hosts]
        y_i6 = [results[host]["i6"][channel] for host in ordered_hosts]
        y_v48 = [results[host]["v48"][channel] for host in ordered_hosts]
        y_i48 = [results[host]["i48"][channel] for host in ordered_hosts]
        ax_v6.plot(x_positions, y_v6, marker="o", linestyle="-", label=f"ch{channel}")
        ax_i6.plot(x_positions, y_i6, marker="o", linestyle="-", label=f"ch{channel}")
        ax_v48.plot(x_positions, y_v48, marker="o", linestyle="-", label=f"ch{channel}")
        ax_i48.plot(x_positions, y_i48, marker="o", linestyle="-", label=f"ch{channel}")

    ax_v6.set_ylabel("V6 [V]")
    ax_v6.set_title(title)
    ax_v6.grid(True, alpha=0.3)
    ax_v6.legend(title="LV Channel", ncols=3)
    ax_i6.set_ylabel("I6 [A]")
    ax_i6.set_title("I6")
    ax_i6.grid(True, alpha=0.3)
    ax_i6.legend(title="LV Channel", ncols=3)
    ax_v48.set_ylabel("V48 [V]")
    ax_v48.set_title("V48")
    ax_v48.grid(True, alpha=0.3)
    ax_v48.legend(title="LV Channel", ncols=3)
    ax_i48.set_ylabel("I48 [A]")
    ax_i48.set_title("I48")
    ax_i48.grid(True, alpha=0.3)
    ax_i48.legend(title="LV Channel", ncols=3)
    ax_v48.set_xticks(x_positions, ordered_hosts, rotation=45, ha="right")
    ax_i48.set_xticks(x_positions, ordered_hosts, rotation=45, ha="right")
    ax_v48.set_xlabel("Box")
    ax_i48.set_xlabel("Box")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)


def live_plot_v6(hosts, args, header, ssh_mode):
    ordered_hosts = sorted(hosts, key=lambda name: int(name.rsplit("psu", 1)[1]))
    history = deque()
    history_window = datetime.timedelta(seconds=args.history)
    voltage_lines = {}
    current_lines = {}
    voltage48_lines = {}
    current48_lines = {}
    log_path, (log_handle, data_logger) = make_data_logger(args, ordered_hosts)
    persistent_connections = {}
    latest_results = {}
    latest_failures = {}
    state_lock = threading.Lock()
    stop_event = threading.Event()

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    ax_v6, ax_i6 = axes[0]
    ax_v48, ax_i48 = axes[1]
    for host in ordered_hosts:
        for channel in range(LV_CHANNELS):
            voltage_line, = ax_v6.plot([], [], marker="o", linestyle="-", linewidth=1, markersize=3)
            current_line, = ax_i6.plot([], [], marker="o", linestyle="-", linewidth=1, markersize=3)
            voltage48_line, = ax_v48.plot([], [], marker="o", linestyle="-", linewidth=1, markersize=3)
            current48_line, = ax_i48.plot([], [], marker="o", linestyle="-", linewidth=1, markersize=3)
            voltage_lines[(host, channel)] = voltage_line
            current_lines[(host, channel)] = current_line
            voltage48_lines[(host, channel)] = voltage48_line
            current48_lines[(host, channel)] = current48_line

    ax_v6.set_ylabel("V6 [V]")
    ax_v6.set_title("V6 Time Series (live)")
    ax_v6.grid(True, alpha=0.3)
    ax_v6.invert_xaxis()
    ax_i6.set_ylabel("I6 [A]")
    ax_i6.set_title("I6 Time Series (live)")
    ax_i6.grid(True, alpha=0.3)
    ax_i6.invert_xaxis()
    ax_v48.set_ylabel("V48 [V]")
    ax_v48.set_title("V48 Time Series (live)")
    ax_v48.grid(True, alpha=0.3)
    ax_v48.invert_xaxis()
    ax_i48.set_ylabel("I48 [A]")
    ax_i48.set_title("I48 Time Series (live)")
    ax_i48.grid(True, alpha=0.3)
    ax_i48.invert_xaxis()
    ax_v48.set_xlabel("Time Ago [s]")
    ax_i48.set_xlabel("Time Ago [s]")

    for host in ordered_hosts:
        persistent_connections[host] = PersistentPsuConnection(
            host,
            args.user,
            args.gateway,
            args.remote_port,
            header,
            ssh_mode,
        )
    for host, connection in persistent_connections.items():
        connection.connect()

    def poll_host(host):
        connection = persistent_connections[host]
        while not stop_event.is_set():
            try:
                measurements = {
                    "v6": connection.query_v6(),
                    "i6": connection.query_i6(),
                    "v48": connection.query_v48(),
                    "i48": connection.query_i48(),
                }
                with state_lock:
                    latest_results[host] = measurements
                    latest_failures.pop(host, None)
            except Exception as exc:
                with state_lock:
                    latest_failures[host] = str(exc)
                    latest_results.pop(host, None)
            if stop_event.wait(args.interval):
                break

    poll_threads = []
    for host in ordered_hosts:
        thread = threading.Thread(target=poll_host, args=(host,), daemon=True, name=f"poll-{host}")
        thread.start()
        poll_threads.append(thread)

    def update(_frame):
        timestamp = now()
        with state_lock:
            results = dict(latest_results)
            failures = dict(latest_failures)
        if not results:
            ax_v6.set_title("V6 Time Series (live) - no data")
            ax_i6.set_title("I6 Time Series (live) - no data")
            ax_v48.set_title("V48 Time Series (live) - no data")
            ax_i48.set_title("I48 Time Series (live) - no data")
            return (
                list(voltage_lines.values())
                + list(current_lines.values())
                + list(voltage48_lines.values())
                + list(current48_lines.values())
            )

        data_logger(timestamp, results)
        history.append((timestamp, results))
        while history and timestamp - history[0][0] > history_window:
            history.popleft()

        all_v6_values = []
        all_i6_values = []
        all_v48_values = []
        all_i48_values = []
        for host in ordered_hosts:
            for channel in range(LV_CHANNELS):
                voltage_line = voltage_lines[(host, channel)]
                current_line = current_lines[(host, channel)]
                voltage48_line = voltage48_lines[(host, channel)]
                current48_line = current48_lines[(host, channel)]
                xx = []
                yy_v6 = []
                yy_i6 = []
                yy_v48 = []
                yy_i48 = []
                for sample_time, sample_results in history:
                    if host not in sample_results:
                        continue
                    xx.append((timestamp - sample_time).total_seconds())
                    yy_v6.append(sample_results[host]["v6"][channel])
                    yy_i6.append(sample_results[host]["i6"][channel])
                    yy_v48.append(sample_results[host]["v48"][channel])
                    yy_i48.append(sample_results[host]["i48"][channel])
                voltage_line.set_data(xx, yy_v6)
                current_line.set_data(xx, yy_i6)
                voltage48_line.set_data(xx, yy_v48)
                current48_line.set_data(xx, yy_i48)
                all_v6_values.extend(yy_v6)
                all_i6_values.extend(yy_i6)
                all_v48_values.extend(yy_v48)
                all_i48_values.extend(yy_i48)

        if all_v6_values:
            ymin = min(all_v6_values)
            ymax = max(all_v6_values)
            padding = max(0.02, (ymax - ymin) * 0.1)
            ax_v6.set_ylim(ymin - padding, ymax + padding)
        if all_i6_values:
            ymin = min(all_i6_values)
            ymax = max(all_i6_values)
            padding = max(0.02, (ymax - ymin) * 0.1 or 0.001)
            ax_i6.set_ylim(ymin - padding, ymax + padding)
        if all_v48_values:
            ymin = min(all_v48_values)
            ymax = max(all_v48_values)
            padding = max(0.02, (ymax - ymin) * 0.1)
            ax_v48.set_ylim(ymin - padding, ymax + padding)
        if all_i48_values:
            ymin = min(all_i48_values)
            ymax = max(all_i48_values)
            padding = max(0.02, (ymax - ymin) * 0.1 or 0.001)
            ax_i48.set_ylim(ymin - padding, ymax + padding)
        ax_v6.set_xlim(args.history, 0)
        ax_i6.set_xlim(args.history, 0)
        ax_v48.set_xlim(args.history, 0)
        ax_i48.set_xlim(args.history, 0)

        failure_count = len(failures)
        ax_v6.set_title(
            f"V6 Time Series (live) - updated {time.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{len(results)}/{len(hosts)} boxes"
            + (f", {failure_count} failed" if failure_count else "")
        )
        ax_i6.set_title(
            f"I6 Time Series (live) - updated {time.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{len(results)}/{len(hosts)} boxes"
            + (f", {failure_count} failed" if failure_count else "")
        )
        ax_v48.set_title(
            f"V48 Time Series (live) - updated {time.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{len(results)}/{len(hosts)} boxes"
            + (f", {failure_count} failed" if failure_count else "")
        )
        ax_i48.set_title(
            f"I48 Time Series (live) - updated {time.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{len(results)}/{len(hosts)} boxes"
            + (f", {failure_count} failed" if failure_count else "")
        )
        return (
            list(voltage_lines.values())
            + list(current_lines.values())
            + list(voltage48_lines.values())
            + list(current48_lines.values())
        )

    animation = FuncAnimation(
        fig,
        update,
        interval=max(200, int(args.interval * 1000)),
        blit=False,
        cache_frame_data=False,
    )
    plt.tight_layout()
    try:
        plt.show()
    finally:
        stop_event.set()
        for thread in poll_threads:
            thread.join(timeout=max(1.0, args.interval + 1.0))
        for connection in persistent_connections.values():
            connection.close()
        log_handle.close()
    return animation


def live_log_only(hosts, args, header, ssh_mode):
    ordered_hosts = sorted(hosts, key=lambda name: int(name.rsplit("psu", 1)[1]))
    log_path, (log_handle, data_logger) = make_data_logger(args, ordered_hosts)
    persistent_connections = {}
    latest_results = {}
    latest_failures = {}
    state_lock = threading.Lock()
    stop_event = threading.Event()

    for host in ordered_hosts:
        persistent_connections[host] = PersistentPsuConnection(
            host,
            args.user,
            args.gateway,
            args.remote_port,
            header,
            ssh_mode,
        )
    for connection in persistent_connections.values():
        connection.connect()

    def poll_host(host):
        connection = persistent_connections[host]
        while not stop_event.is_set():
            try:
                measurements = {
                    "v6": connection.query_v6(),
                    "i6": connection.query_i6(),
                    "v48": connection.query_v48(),
                    "i48": connection.query_i48(),
                }
                with state_lock:
                    latest_results[host] = measurements
                    latest_failures.pop(host, None)
            except Exception as exc:
                with state_lock:
                    latest_failures[host] = str(exc)
                    latest_results.pop(host, None)
            if stop_event.wait(args.interval):
                break

    poll_threads = []
    for host in ordered_hosts:
        thread = threading.Thread(target=poll_host, args=(host,), daemon=True, name=f"log-poll-{host}")
        thread.start()
        poll_threads.append(thread)

    try:
        while True:
            timestamp = now()
            with state_lock:
                results = dict(latest_results)
            if results:
                data_logger(timestamp, results)
            if stop_event.wait(args.interval):
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        for thread in poll_threads:
            thread.join(timeout=max(1.0, args.interval + 1.0))
        for connection in persistent_connections.values():
            connection.close()
        log_handle.close()


def parse_args():
    default_header = Path(__file__).resolve().parent.parent / "commands.h"
    parser = argparse.ArgumentParser(
        description="Read V6 for all channels on mu2e-trk-psu0..17 and plot each channel across boxes."
    )
    parser.add_argument("--start", type=int, default=DEFAULT_START, help="First PSU index")
    parser.add_argument("--stop", type=int, default=DEFAULT_STOP, help="Last PSU index, inclusive")
    parser.add_argument(
        "--psu",
        type=int,
        help="Monitor only one PSU index, e.g. --psu 6",
    )
    parser.add_argument(
        "--exclude",
        type=int,
        nargs="*",
        default=DEFAULT_EXCLUDE,
        help="PSU indices to skip, e.g. --exclude 6 9",
    )
    parser.add_argument("--user", default=DEFAULT_USER, help="SSH username")
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY, help="SSH jump host")
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT, help="Remote LV/HV server port")
    parser.add_argument("--header", default=str(default_header), help="Local path to commands.h")
    parser.add_argument("--workers", type=int, default=6, help="Parallel PSU queries")
    parser.add_argument("--interval", type=float, default=5.0, help="Refresh period in seconds for live plotting")
    parser.add_argument("--history", type=float, default=300.0, help="Seconds of history to keep in live mode")
    parser.add_argument("--csv-out", default=DEFAULT_CSV_BASENAME, help="Output CSV path")
    parser.add_argument("--sqlite", action="store_true", help="Log to SQLite using Python's built-in sqlite3")
    parser.add_argument("--db-out", default=DEFAULT_DB_BASENAME, help="Output SQLite database path")
    parser.add_argument("--plot-out", default="v6_all_pis.png", help="Output plot image path")
    parser.add_argument(
        "--ssh-mode",
        choices=("config", "explicit", "direct"),
        default="config",
        help="Use SSH host aliases from ~/.ssh/config, explicit jump-host settings, or direct ssh user@host",
    )
    parser.add_argument(
        "--host-prefix",
        default="psu",
        help="Host prefix to use in config mode, e.g. psu -> psu0..psu17",
    )
    parser.add_argument("--live", action="store_true", help="Refresh the plot continuously until closed")
    parser.add_argument("--log-only", action="store_true", help="Continuously log to CSV without opening a plot")
    parser.add_argument("--show", action="store_true", help="Display the plot window")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.csv_out == DEFAULT_CSV_BASENAME:
        args.csv_out = default_csv_path()
    if args.db_out == DEFAULT_DB_BASENAME:
        args.db_out = default_db_path()
    use_ssh_config = args.ssh_mode == "config"
    if args.psu is not None:
        indices = [args.psu]
    else:
        excluded = set(args.exclude)
        indices = [i for i in range(args.start, args.stop + 1) if i not in excluded]

    if use_ssh_config:
        hosts = [f"{args.host_prefix}{i}" for i in indices]
    else:
        hosts = [f"mu2e-trk-psu{i}" for i in indices]
    header = str(Path(args.header).resolve())

    if args.live and args.log_only:
        raise RuntimeError("Use either --live or --log-only, not both")

    if args.log_only:
        live_log_only(hosts, args, header, args.ssh_mode)
        return

    if args.live:
        live_plot_v6(hosts, args, header, args.ssh_mode)
        return

    results, failures = collect_v6(
        hosts,
        args.user,
        args.gateway,
        args.remote_port,
        header,
        args.ssh_mode,
        args.workers,
    )
    rows = rows_from_results(results)

    if not rows:
        raise RuntimeError("No V6 values were collected")

    plot_out = Path(args.plot_out).resolve()
    if args.sqlite:
        db_out = Path(args.db_out).resolve()
        write_sqlite(rows, db_out)
    else:
        csv_out = Path(args.csv_out).resolve()
        write_csv(rows, csv_out)
    plot_v6(results, plot_out, f"V6 Across {len(results)} Boxes")

    print(f"\nCollected {len(rows)} values from {len(results)} PSUs")
    if args.sqlite:
        print(f"DB: {db_out}")
    else:
        print(f"CSV: {csv_out}")
    print(f"Plot: {plot_out}")
    if failures:
        print("\nFailures:")
        for host in sorted(failures, key=lambda name: int(name.rsplit('psu', 1)[1])):
            print(f"  {host}: {failures[host]}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
