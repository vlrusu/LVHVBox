#!/usr/bin/env python3

import argparse
import sqlite3
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export ordered timestamps from an LV/HV SQLite log database."
    )
    parser.add_argument("db_file", help="Input SQLite database file")
    parser.add_argument(
        "--output",
        default="timestamps.txt",
        help="Output text file for timestamps",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db_file).resolve()
    output_path = Path(args.output).resolve()

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        timestamps = cur.execute(
            "SELECT DISTINCT timestamp FROM measurements ORDER BY timestamp"
        )
        with output_path.open("w") as handle:
            for (timestamp,) in timestamps:
                handle.write(f"{timestamp}\n")
    finally:
        con.close()

    print(output_path)


if __name__ == "__main__":
    main()
