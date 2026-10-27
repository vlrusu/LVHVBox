#!/usr/bin/env python3

import argparse
import csv
import datetime
import os
import sqlite3
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot V6/I6/V48/I48 from an offline LV/HV monitor CSV or SQLite file."
    )
    parser.add_argument("csv_file", help="Input CSV or SQLite file, e.g. v6_all_pis_20260506_113843.csv or .db")
    parser.add_argument("--output", help="Output image path. Defaults to input name with .png")
    parser.add_argument("--psu", type=int, help="Plot only one PSU index, e.g. --psu 16")
    parser.add_argument(
        "--psu-by-psu",
        action="store_true",
        help="Generate one output plot per PSU",
    )
    parser.add_argument("--show", action="store_true", help="Open the plot interactively")
    parser.add_argument(
        "--start-time",
        help="Inclusive ISO timestamp lower bound, e.g. 2026-05-06T15:24:30",
    )
    parser.add_argument(
        "--stop-time",
        help="Inclusive ISO timestamp upper bound, e.g. 2026-05-06T15:28:00",
    )
    parser.add_argument(
        "--drop-last-minutes",
        type=float,
        default=0.0,
        help="Drop this many minutes from the end of the file before plotting",
    )
    return parser.parse_args()


def configure_matplotlib(show):
    if not show:
        os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib.pyplot as plt
    return plt


def load_rows(csv_path):
    if csv_path.suffix in (".db", ".sqlite", ".sqlite3"):
        return load_rows_from_sqlite(csv_path)
    with csv_path.open() as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"No rows found in {csv_path}")
    return rows


def load_rows_from_sqlite(db_path):
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        query = """
            SELECT timestamp, host, channel, v6, i6, v48, i48
            FROM measurements
            ORDER BY timestamp, host, channel
        """
        fetched_rows = cursor.execute(query).fetchall()
    finally:
        connection.close()

    if not fetched_rows:
        raise RuntimeError(f"No rows found in {db_path}")

    by_timestamp = {}
    timestamp_order = []
    for timestamp, host, channel, v6, i6, v48, i48 in fetched_rows:
        if timestamp not in by_timestamp:
            by_timestamp[timestamp] = {"timestamp": timestamp}
            timestamp_order.append(timestamp)
        row = by_timestamp[timestamp]
        row[f"{host}_ch{channel}_v6"] = v6
        row[f"{host}_ch{channel}_i6"] = i6
        row[f"{host}_ch{channel}_v48"] = v48
        row[f"{host}_ch{channel}_i48"] = i48

    return [by_timestamp[timestamp] for timestamp in timestamp_order]


def parse_optional_time(value, option_name):
    if value is None:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid {option_name}: {value}") from exc


def filter_rows(rows, drop_last_minutes, start_time, stop_time):
    timestamps = [datetime.datetime.fromisoformat(row["timestamp"]) for row in rows]

    effective_stop_time = stop_time
    if drop_last_minutes > 0:
        drop_cutoff = timestamps[-1] - datetime.timedelta(minutes=drop_last_minutes)
        effective_stop_time = drop_cutoff if effective_stop_time is None else min(effective_stop_time, drop_cutoff)

    filtered = []
    for ts, row in zip(timestamps, rows):
        if start_time is not None and ts < start_time:
            continue
        if effective_stop_time is not None and effective_stop_time < ts:
            continue
        filtered.append((ts, row))
    if not filtered:
        raise RuntimeError("No data left after applying time filters")
    return [ts for ts, _ in filtered], [row for _, row in filtered]


def extract_psu_index(key):
    host_part = key.split("_ch", 1)[0]
    if "psu" not in host_part:
        raise ValueError(f"Cannot extract PSU index from {key}")
    return int(host_part.rsplit("psu", 1)[1])


def measurement_keys(row, suffix):
    return sorted(
        [key for key in row.keys() if key.endswith(suffix)],
        key=lambda key: (
            extract_psu_index(key),
            int(key.split("_ch", 1)[1].split("_", 1)[0]),
        ),
    )


def measurement_keys_for_psu(row, suffix, psu_index):
    return [key for key in measurement_keys(row, suffix) if extract_psu_index(key) == psu_index]


def values_for(rows, key):
    return [float(row[key]) if row[key] else float("nan") for row in rows]


def plot_panel(ax, x_values, rows, keys, title, ylabel):
    for key in keys:
        ax.plot(x_values, values_for(rows, key), linewidth=1.0)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)


def available_psus(row):
    psus = sorted(
        {
            extract_psu_index(key)
            for key in row.keys()
            if key != "timestamp" and "_ch" in key
        }
    )
    return psus


def make_output_path(csv_path, output_path, psu_index):
    if output_path is None:
        return csv_path.with_name(f"{csv_path.stem}_psu{psu_index}.png")
    return output_path.with_name(f"{output_path.stem}_psu{psu_index}{output_path.suffix}")


def create_figure(plt, minutes, rows, title, psu_index=None):
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    ax_v6, ax_i6 = axes[0]
    ax_v48, ax_i48 = axes[1]

    key_fn = measurement_keys if psu_index is None else lambda row, suffix: measurement_keys_for_psu(row, suffix, psu_index)
    plot_panel(ax_v6, minutes, rows, key_fn(rows[0], "_v6"), "V6", "V6 [V]")
    plot_panel(ax_i6, minutes, rows, key_fn(rows[0], "_i6"), "I6", "I6 [A]")
    plot_panel(ax_v48, minutes, rows, key_fn(rows[0], "_v48"), "V48", "V48 [V]")
    plot_panel(ax_i48, minutes, rows, key_fn(rows[0], "_i48"), "I48", "I48 [A]")

    ax_v48.set_xlabel("Time Since Start [min]")
    ax_i48.set_xlabel("Time Since Start [min]")
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def main():
    args = parse_args()
    plt = configure_matplotlib(args.show)
    csv_path = Path(args.csv_file).resolve()
    output_path = Path(args.output).resolve() if args.output else None

    rows = load_rows(csv_path)
    start_time = parse_optional_time(args.start_time, "--start-time")
    stop_time = parse_optional_time(args.stop_time, "--stop-time")
    if start_time is not None and stop_time is not None and stop_time < start_time:
        raise RuntimeError("--stop-time must be greater than or equal to --start-time")
    timestamps, rows = filter_rows(rows, args.drop_last_minutes, start_time, stop_time)
    t0 = timestamps[0]
    minutes = [(ts - t0).total_seconds() / 60.0 for ts in timestamps]
    psus = available_psus(rows[0])

    if args.psu_by_psu:
        output_paths = []
        for psu_index in psus:
            fig = create_figure(plt, minutes, rows, f"{csv_path.name} - psu{psu_index}", psu_index=psu_index)
            psu_output_path = make_output_path(csv_path, output_path, psu_index)
            fig.savefig(psu_output_path, dpi=150)
            output_paths.append(psu_output_path)
            plt.close(fig)
        for path in output_paths:
            print(path)
        return

    selected_psu = args.psu
    if selected_psu is not None and selected_psu not in psus:
        raise RuntimeError(f"psu{selected_psu} not found in {csv_path.name}")

    title = csv_path.name if selected_psu is None else f"{csv_path.name} - psu{selected_psu}"
    fig = create_figure(plt, minutes, rows, title, psu_index=selected_psu)
    output_path = output_path if output_path is not None else csv_path.with_suffix(".png")
    fig.savefig(output_path, dpi=150)
    if args.show:
        plt.show()
    plt.close(fig)
    print(output_path)


if __name__ == "__main__":
    main()
