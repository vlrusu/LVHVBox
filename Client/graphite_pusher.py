#!/usr/bin/env python3

import argparse
import math
import re
import signal
import socket
import threading
import time

from PiHealthConnection import PiHealthConnection
from PowerSupplyServerConnection import PowerSupplyServerConnection


stop_event = threading.Event()


def handle_signal(_signum, _frame):
    stop_event.set()


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


def collect_lv_metrics(psu, prefix, timestamp):
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


def collect_hv_metrics(psu, prefix, timestamp):
    lines = []
    for channel, value in enumerate(psu.QueryWireVoltages()):
        add_numeric_metric(lines, f"{prefix}.channels.ch{channel}.vhv_v", value, timestamp)
    for channel, value in enumerate(psu.QueryWireCurrents()):
        add_numeric_metric(lines, f"{prefix}.channels.ch{channel}.ihv_ua", value, timestamp)

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


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return seconds


def parse_args(argv=None):
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
    parser.add_argument("--interval", type=positive_seconds, default=20.0,
                        help="LV, board temperature, and Pi-health interval in seconds (default: 20)")
    parser.add_argument("--hv-interval", type=positive_seconds, default=1.0,
                        help="HV voltage/current interval in seconds (default: 1)")
    parser.add_argument("--timeout", type=positive_seconds, default=5.0, help="Network timeout in seconds")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect metrics and print Graphite plaintext lines instead of sending them",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect each group once and exit",
    )
    return parser.parse_args(argv)


def publish_metrics(args, lines):
    if args.dry_run:
        emit_test_output(lines)
    else:
        send_graphite(lines, args.graphite_host, args.graphite_port, args.timeout)


def collection_worker(args, metric_prefix, group):
    # A connection belongs exclusively to this worker. Never interleave two
    # request/reply streams on the same LVHV socket.
    interval = args.hv_interval if group == "hv" else args.interval
    success_path = f"{metric_prefix}.collector.hv.success" if group == "hv" else f"{metric_prefix}.collector.success"
    power_connection = None
    health_connection = PiHealthConnection(args.health_host, args.health_port, timeout=args.timeout) if group == "slow" else None
    next_cycle = time.monotonic()
    try:
        while not stop_event.is_set():
            timestamp = int(time.time())
            try:
                if power_connection is None:
                    power_connection = PowerSupplyServerConnection(args.lvhv_host, args.lvhv_port, args.header)
                if group == "hv":
                    lines = collect_hv_metrics(power_connection, metric_prefix, timestamp)
                else:
                    lines = collect_lv_metrics(power_connection, metric_prefix, timestamp)
                    lines.extend(collect_health_metrics(health_connection, metric_prefix, timestamp))
                add_numeric_metric(lines, success_path, 1, timestamp)
                publish_metrics(args, lines)
            except Exception as exc:
                print(f"graphite {group} collection cycle failed: {exc}", flush=True)
                if power_connection is not None:
                    power_connection.close()
                    power_connection = None
                try:
                    publish_metrics(args, [graphite_line(success_path, 0, timestamp)])
                except Exception as send_exc:
                    print(f"graphite {group} failure status could not be sent: {send_exc}", flush=True)

            if args.once:
                break

            # Keep a steady cadence using a clock unaffected by NTP changes.
            # Skip missed slots instead of sending a burst of catch-up samples.
            next_cycle += interval
            now = time.monotonic()
            if next_cycle < now:
                next_cycle += (math.floor((now - next_cycle) / interval) + 1) * interval
            stop_event.wait(max(0, next_cycle - time.monotonic()))
    finally:
        if power_connection is not None:
            power_connection.close()


def main():
    args = parse_args()
    stop_event.clear()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    metric_node = args.metric_node or infer_metric_node()
    metric_prefix = f"{args.metric_root}.{metric_node}"
    workers = [
        threading.Thread(target=collection_worker, args=(args, metric_prefix, group),
                         name=f"graphite-{group}", daemon=True)
        for group in ("hv", "slow")
    ]
    for worker in workers:
        worker.start()
    while not stop_event.is_set() and any(worker.is_alive() for worker in workers):
        stop_event.wait(0.2)
    # Do not let a stalled hardware read prevent systemd from stopping us.
    for worker in workers:
        worker.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
