#!/usr/bin/env python3

import argparse
import re
import signal
import socket
import time
from datetime import datetime, timezone

from PiHealthConnection import PiHealthConnection
from PowerSupplyServerConnection import PowerSupplyServerConnection


running = True


def handle_signal(_signum, _frame):
    global running
    running = False


def sanitize_metric_component(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value)


def infer_metric_node():
    return sanitize_metric_component(socket.gethostname().split(".", 1)[0])


def graphite_line(path, value, timestamp):
    return f"{path} {value} {timestamp}"


def add_numeric_metric(lines, path, value, timestamp):
    if value is None:
        return
    if isinstance(value, bool):
        value = int(value)
    lines.append(graphite_line(path, value, timestamp))


def boolish_to_int(value):
    if value is None:
        return None
    return 1 if value else 0


def collect_power_metrics(psu, prefix, timestamp):
    lines = []

    for channel, value in enumerate(psu.QueryPowerVoltages()):
        add_numeric_metric(lines, f"{prefix}.channels.ch{channel}.v48_v", value, timestamp)
    for channel, value in enumerate(psu.QueryPowerCurrents()):
        add_numeric_metric(lines, f"{prefix}.channels.ch{channel}.i48_a", value, timestamp)
    for channel, value in enumerate(psu.QuerySwitchingVoltages()):
        add_numeric_metric(lines, f"{prefix}.channels.ch{channel}.v6_v", value, timestamp)
    for channel, value in enumerate(psu.QuerySwitchingCurrents()):
        add_numeric_metric(lines, f"{prefix}.channels.ch{channel}.i6_a", value, timestamp)

    add_numeric_metric(lines, f"{prefix}.pcb_temp_c", psu.QueryPcbTemp(), timestamp)
    return lines


def collect_health_metrics(health, prefix, timestamp):
    lines = []
    payload = health.get_health()
    gpio6 = payload.get("ac_inputs", {}).get("gpio6_ac_status", {})
    add_numeric_metric(
        lines,
        f"{prefix}.ac.gpio6_present",
        boolish_to_int(gpio6.get("ac_power_present")),
        timestamp,
    )

    add_numeric_metric(lines, f"{prefix}.battery.voltage_v", payload.get("battery_voltage_v"), timestamp)
    add_numeric_metric(lines, f"{prefix}.battery.capacity_pct", payload.get("battery_capacity_pct"), timestamp)
    add_numeric_metric(
        lines,
        f"{prefix}.battery.error",
        0 if payload.get("battery_error") in (None, "") else 1,
        timestamp,
    )

    return lines


def send_graphite(lines, host, port, timeout):
    if not lines:
        return
    payload = ("\n".join(lines) + "\n").encode("ascii")
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(payload)


def emit_test_output(lines):
    if not lines:
        print("# no metrics collected")
        return
    for line in lines:
        print(line)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Push local LV/HV and Pi health metrics from a PSU node to Graphite."
    )
    parser.add_argument("--lvhv-host", default="127.0.0.1", help="Local LV/HV server host")
    parser.add_argument("--lvhv-port", type=int, default=12000, help="Local LV/HV server port")
    parser.add_argument(
        "--health-host",
        default="127.0.0.1",
        help="Local Pi health HTTP server host",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=12002,
        help="Local Pi health HTTP server port",
    )
    parser.add_argument(
        "--header",
        default="/etc/mu2e-tracker-lvhv-tools/commands.h",
        help="Path to opcode macro header",
    )
    parser.add_argument(
        "--graphite-host",
        default="mu2e-dcs-01.fnal.gov",
        help="Graphite/Carbon plaintext receiver host",
    )
    parser.add_argument(
        "--graphite-port",
        type=int,
        default=2003,
        help="Graphite/Carbon plaintext receiver port",
    )
    parser.add_argument("--metric-root", default="mu2etrk.lvhv", help="Metric root prefix")
    parser.add_argument(
        "--metric-node",
        default=None,
        help="Per-PSU metric node; defaults to the local hostname",
    )
    parser.add_argument("--interval", type=float, default=10.0, help="Polling interval in seconds")
    parser.add_argument("--timeout", type=float, default=5.0, help="Network timeout in seconds")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect metrics and print Graphite plaintext lines instead of sending them",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collection cycle and exit",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    metric_node = args.metric_node or infer_metric_node()
    metric_prefix = f"{args.metric_root}.{metric_node}"

    power_connection = PowerSupplyServerConnection(args.lvhv_host, args.lvhv_port, args.header)
    health_connection = PiHealthConnection(args.health_host, args.health_port, timeout=args.timeout)
    while running:
        cycle_start = time.time()
        timestamp = int(cycle_start)
        try:
            lines = []
            lines.extend(collect_power_metrics(power_connection, metric_prefix, timestamp))
            lines.extend(collect_health_metrics(health_connection, metric_prefix, timestamp))
            add_numeric_metric(lines, f"{metric_prefix}.collector.success", 1, timestamp)
            if args.dry_run:
                emit_test_output(lines)
            else:
                send_graphite(lines, args.graphite_host, args.graphite_port, args.timeout)
        except Exception as exc:
            print(f"graphite push cycle failed: {exc}")
            try:
                power_connection.reestablish()
            except Exception as reconnect_exc:
                print(f"power connection reestablish failed: {reconnect_exc}")
            if args.dry_run:
                print(graphite_line(f"{metric_prefix}.collector.success", 0, timestamp))
            else:
                try:
                    send_graphite(
                        [graphite_line(f"{metric_prefix}.collector.success", 0, timestamp)],
                        args.graphite_host,
                        args.graphite_port,
                        args.timeout,
                    )
                except Exception:
                    pass

        if args.once:
            break

        elapsed = time.time() - cycle_start
        sleep_for = args.interval - elapsed
        if running and 0 < sleep_for:
            time.sleep(sleep_for)

    power_connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
