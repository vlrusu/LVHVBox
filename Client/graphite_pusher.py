#!/usr/bin/env python3

import argparse
import math
import os
import queue
from datetime import datetime, timezone
import re
import signal
import socket
import threading
import time

from RS485Connection import RS485Connection
from PiHealthConnection import PiHealthConnection
from PowerSupplyServerConnection import PowerSupplyServerConnection


stop_event = threading.Event()

# Values/conversions are supplied by rs485-server, including the per-panel Flow
# calibration. Dots in rail names are sanitized into one Graphite path component.
RS485_DIRECT_PARAMETERS = ('ROC_TEMP', 'ROC_RAIL_1V', 'ROC_RAIL_1.8V', 'ROC_RAIL_2.5V')
RS485_CPU_PARAMETERS = ('Flow', 'V5KEY', 'V2.5KEY', 'DCDCTEMP')


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


class RS485PowerGate:
    """Read-only, whole-PSU V6 gate; cache briefly during long RS485 scans."""
    def __init__(self, psu):
        self.psu = psu
        self.powered = None
        self.checked_at = None

    def __call__(self, force=False):
        now = time.monotonic()
        if force or self.checked_at is None or now - self.checked_at >= 5:
            values = self.psu.QuerySwitchingVoltages()
            if (not isinstance(values, (list, tuple)) or len(values) != 6 or
                    any(type(v) not in (int, float) or not math.isfinite(v) or v <= -1
                        for v in values)):
                raise ValueError('Invalid V6 readings; RS485 power state unknown')
            powered = any(v >= 2 for v in values)
            if powered != self.powered:
                status = ('ON: polling all discovered panels' if powered else
                          'OFF: skipping panel reads (all six V6 below 2 V)')
                print(f'graphite rs485 PSU {status}', flush=True)
            self.powered = powered
            self.checked_at = time.monotonic()
        return self.powered


def collect_rs485_metrics(rs485, prefix, power_gate):
    if not power_gate(force=True):
        return [], None  # intentionally disabled, not a readout failure
    # Cached discovery only: polling never initiates a new address scan.
    inventory = rs485.get_panels()
    if inventory.get('scanned') is not True:
        raise ValueError('RS485 startup discovery has not completed')
    addresses = inventory.get('addresses')
    if (not isinstance(addresses, list) or
            any(type(address) is not int or not 0 <= address <= 511 for address in addresses) or
            len(set(addresses)) != len(addresses)):
        raise ValueError('Invalid RS485 panel inventory')
    lines = []
    add_numeric_metric(lines, f'{prefix}.collector.rs485.panels', len(addresses), int(time.time()))
    all_ok = bool(addresses)
    for address in addresses:
        if stop_event.is_set():
            return lines, False
        panel_prefix = f'{prefix}.panels.MN{address:03d}'
        panel_ok = True
        for name in (*RS485_DIRECT_PARAMETERS, *RS485_CPU_PARAMETERS):
            if stop_event.is_set():
                return lines, False
            if not power_gate():
                return lines, None
            try:
                read = rs485.direct_read if name in RS485_DIRECT_PARAMETERS else rs485.read
                value = read(address, name)['value']
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError('RS485 result is not a finite numeric value')
                add_numeric_metric(lines, f'{panel_prefix}.{sanitize_metric_component(name)}',
                                   value, int(time.time()))
            except Exception as exc:
                # Keep successful FPGA values even if the CPU/Flow read fails.
                # No fallback, no immediate retry and no fabricated zero sample.
                panel_ok = False
                print(f'graphite rs485 MN{address:03d} {name} failed: {exc}', flush=True)
        add_numeric_metric(lines, f'{panel_prefix}.collector.success', int(panel_ok), int(time.time()))
        all_ok = all_ok and panel_ok
    return lines, all_ok


def send_graphite(lines, host, port, timeout):
    if not lines:
        return
    payload = ("\n".join(lines) + "\n").encode("ascii")
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(payload)


# Optional sink; only the database thread owns its connection and channel cache.
postgres_writer = None


def postgres_sample(line, metric_root, metric_node):
    path, raw_value, raw_time = line.split()
    prefix = f"{metric_root}.{metric_node}."
    if not path.startswith(prefix):
        raise ValueError("Metric outside configured PSU prefix")
    suffix = path[len(prefix):]
    match = re.fullmatch(r"channels\.ch(\d+)\.(vhv_v|ihv_ua)", suffix)
    if match is None:
        raise ValueError("PostgreSQL output accepts HV voltage/current only")
    channel = int(match.group(1))
    units = {"vhv_v": "V", "ihv_ua": "uA"}
    leaf = match.group(2)
    value = float(raw_value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite PostgreSQL sample")
    return (path, metric_node, channel, units.get(leaf),
            datetime.fromtimestamp(int(raw_time), timezone.utc), value)


class PostgresWriter:
    def __init__(self, args, connect):
        self.args = args
        self.connect = connect
        self.pending = queue.Queue(maxsize=args.postgres_queue_size)
        self.finished = threading.Event()
        self.connection = None
        self.channel_ids = {}
        self.thread = threading.Thread(target=self.run, name="postgres-writer", daemon=True)

    def submit(self, lines):
        prefix = f"{self.args.metric_root}.{self.args.metric_node}."
        lines = tuple(line for line in lines if re.fullmatch(
            re.escape(prefix) + r"channels\.ch\d+\.(vhv_v|ihv_ua)", line.split()[0]))
        if not lines:
            return
        try:
            self.pending.put_nowait(tuple(lines))
        except queue.Full:
            print("postgres queue full; dropped newest batch", flush=True)

    def write_batch(self, lines):
        samples = [postgres_sample(line, self.args.metric_root, self.args.metric_node)
                   for line in lines]
        if self.connection is None:
            # Connection settings come from libpq PG* environment/service files.
            # Never print a DSN, driver exception text, or credentials.
            self.connection = self.connect(
                connect_timeout=5, application_name="mu2e-graphite-pusher",
                options="-c statement_timeout=5000 -c lock_timeout=5000")
            self.connection.set_session(isolation_level="READ COMMITTED")
        new_ids = {}
        with self.connection:
            with self.connection.cursor() as cursor:
                unresolved = any(sample[0] not in self.channel_ids for sample in samples)
                if unresolved and self.args.postgres_register_channels:
                    # Serialize registration between instances of this pusher.
                    # Other channel writers should enforce the same identity via UNIQUE.
                    cursor.execute("SELECT pg_advisory_xact_lock(73482901)")
                values = []
                for name, psu, channel, unit, timestamp, value in samples:
                    channel_id = self.channel_ids.get(name, new_ids.get(name))
                    if channel_id is None:
                        cursor.execute(
                            "SELECT id FROM trk_channel WHERE name = %s AND psu = %s "
                            "AND channel = %s", (name, psu, channel))
                        rows = cursor.fetchall()
                        if len(rows) > 1:
                            raise ValueError("Ambiguous PostgreSQL channel identity")
                        if rows:
                            channel_id = rows[0][0]
                        elif self.args.postgres_register_channels:
                            # id must have a sequence/identity default supplied by the DB.
                            cursor.execute(
                                "INSERT INTO trk_channel (name, psu, channel, unit) "
                                "VALUES (%s, %s, %s, %s) RETURNING id",
                                (name, psu, channel, unit))
                            channel_id = cursor.fetchone()[0]
                        else:
                            raise ValueError("Missing PostgreSQL channel; registration disabled")
                        new_ids[name] = channel_id
                    values.append((timestamp, channel_id, value))
                cursor.executemany(
                    "INSERT INTO trk_value (time, channel_id, value) VALUES (%s, %s, %s)",
                    values)
        # Cache only committed IDs; a rolled-back registration must be retried.
        self.channel_ids.update(new_ids)

    def run(self):
        try:
            while not self.finished.is_set() or not self.pending.empty():
                try:
                    lines = self.pending.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    self.write_batch(lines)
                except Exception as exc:
                    print(f"postgres batch failed ({type(exc).__name__}); batch dropped; "
                          "check connectivity, permissions and channel metadata", flush=True)
                    if self.connection is not None:
                        self.connection.close()
                        self.connection = None
                    self.channel_ids.clear()
                    # No retry: a lost commit reply has an ambiguous outcome.
                    # Back off the DB thread without delaying any collector.
                    self.finished.wait(5)
                finally:
                    self.pending.task_done()
        finally:
            if self.connection is not None:
                self.connection.close()

    def close(self):
        self.finished.set()
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            print("postgres shutdown deadline reached; queued samples may be lost", flush=True)


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
        description="Export local telemetry to Graphite and/or HV data to PostgreSQL."
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
    parser.add_argument("--no-graphite-hv", action="store_true",
                        default=os.environ.get("MU2E_GRAPHITE_HV_ENABLED") == "0",
                        help="Send HV voltage/current only to PostgreSQL; keep other Graphite telemetry")
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
    parser.add_argument("--rs485-host", default="127.0.0.1", help="RS485 HTTP server host")
    parser.add_argument("--rs485-port", type=int, default=12004, help="RS485 HTTP server port")
    parser.add_argument("--rs485-interval", type=positive_seconds, default=20.0,
                        help="FPGA TVS and calibrated Flow interval in seconds (default: 20)")
    parser.add_argument("--rs485-timeout", type=positive_seconds, default=30.0,
                        help="RS485 HTTP timeout, allowing CPU replies and bus holdoff (default: 30)")
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
    parser.add_argument("--postgres", action="store_true",
                        default=os.environ.get("MU2E_POSTGRES_ENABLED") == "1",
                        help="Also insert HV voltage/current into PostgreSQL using libpq PG* settings")
    parser.add_argument("--postgres-register-channels", action="store_true",
                        default=os.environ.get("MU2E_POSTGRES_REGISTER_CHANNELS") == "1",
                        help="Create missing trk_channel rows (requires an id default)")
    parser.add_argument("--postgres-queue-size", type=int, default=120,
                        help="Maximum in-memory PostgreSQL batches (default: 120)")
    args = parser.parse_args(argv)
    if args.postgres_queue_size <= 0:
        parser.error("--postgres-queue-size must be greater than zero")
    if args.no_graphite_hv and not args.postgres and not args.dry_run:
        parser.error("--no-graphite-hv requires --postgres (or --dry-run)")
    return args


def publish_metrics(args, lines):
    if args.dry_run:
        emit_test_output(lines)
    else:
        if postgres_writer is not None:
            postgres_writer.submit(lines)
        graphite_lines = lines
        if args.no_graphite_hv:
            # Only the two archived HV measurements are suppressed; collector
            # status and all LV/health/RS485 telemetry retain their destinations.
            graphite_lines = [line for line in lines
                              if not re.fullmatch(re.escape(f"{args.metric_root}.{args.metric_node}.") +
                                                  r"channels\.ch\d+\.(vhv_v|ihv_ua)", line.split()[0])]
        if graphite_lines:
            try:
                send_graphite(graphite_lines, args.graphite_host, args.graphite_port, args.timeout)
            except Exception as exc:
                print(f"graphite send failed ({type(exc).__name__}); batch dropped", flush=True)


def collection_worker(args, metric_prefix, group):
    # A connection belongs exclusively to this worker. Never interleave two
    # request/reply streams on the same LVHV socket.
    interval = {"hv": args.hv_interval, "slow": args.interval, "rs485": args.rs485_interval}[group]
    suffix = {"hv": "collector.hv.success", "slow": "collector.success",
              "rs485": "collector.rs485.success"}[group]
    success_path = f"{metric_prefix}.{suffix}"
    power_connection = None
    health_connection = PiHealthConnection(args.health_host, args.health_port, timeout=args.timeout) if group == "slow" else None
    rs485_connection = None
    power_gate = None
    next_cycle = time.monotonic()
    try:
        while not stop_event.is_set():
            timestamp = int(time.time())
            try:
                if power_connection is None:
                    power_connection = PowerSupplyServerConnection(args.lvhv_host, args.lvhv_port, args.header)
                if group == "rs485":
                    if power_gate is None:
                        power_gate = RS485PowerGate(power_connection)
                    if rs485_connection is None:
                        rs485_connection = RS485Connection(args.rs485_host, args.rs485_port,
                                                           timeout=args.rs485_timeout, client_id='graphite')
                    lines, success = collect_rs485_metrics(rs485_connection, metric_prefix, power_gate)
                    add_numeric_metric(lines, f"{metric_prefix}.collector.rs485.enabled",
                                       int(success is not None), int(time.time()))
                    timestamp = int(time.time())
                else:
                    if group == "hv":
                        lines = collect_hv_metrics(power_connection, metric_prefix, timestamp)
                    else:
                        lines = collect_lv_metrics(power_connection, metric_prefix, timestamp)
                        lines.extend(collect_health_metrics(health_connection, metric_prefix, timestamp))
                    success = True
                if success is not None:
                    add_numeric_metric(lines, success_path, int(success), timestamp)
                publish_metrics(args, lines)
            except Exception as exc:
                print(f"graphite {group} collection cycle failed: {exc}", flush=True)
                if power_connection is not None:
                    power_connection.close()
                    power_connection = None
                    power_gate = None
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
    global postgres_writer
    args = parse_args()
    postgres_writer = None
    if args.postgres and not args.dry_run:
        try:
            import psycopg2
        except ImportError:
            print("PostgreSQL output requires psycopg2 in the service Python interpreter", flush=True)
            return 2
    stop_event.clear()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    metric_node = args.metric_node or infer_metric_node()
    metric_prefix = f"{args.metric_root}.{metric_node}"
    args.metric_node = metric_node
    if args.postgres and not args.dry_run:
        postgres_writer = PostgresWriter(args, psycopg2.connect)
        postgres_writer.thread.start()
    workers = [
        threading.Thread(target=collection_worker, args=(args, metric_prefix, group),
                         name=f"graphite-{group}", daemon=True)
        for group in ("hv", "slow", "rs485")
    ]
    for worker in workers:
        worker.start()
    while not stop_event.is_set() and any(worker.is_alive() for worker in workers):
        stop_event.wait(0.2)
    # Do not let a stalled hardware read prevent systemd from stopping us.
    for worker in workers:
        worker.join(timeout=1.0)
    if postgres_writer is not None:
        postgres_writer.close()
        postgres_writer = None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
