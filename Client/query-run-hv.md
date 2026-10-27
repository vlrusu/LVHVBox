# Query run HV from a laptop

`query_run_hv.py` prints measured HV voltage samples with columns
PSU, Channel, HV_V and Timestamp_UTC. PSU/channel numbers match the zero-based
archive metadata. Values retain database precision; null values are blank.
First it prints the earliest sample for every PSU0–17/channel0–11 combination
(216 rows), sorted by PSU/channel. Missing initial data remains a blank row
and is flagged on stderr. It then prints a dotted separator, followed by later
samples only when the voltage differs by strictly more than500V from that
channel's last printed value, in timestamp order. There is no averaging.
For a null initial voltage, the first subsequent non-null sample establishes
the baseline and is printed. --psu restricts both sections to that PSU's12channels.

```bash
python3 -m venv .venv-hv
source .venv-hv/bin/activate
python3 -m pip install psycopg2-binary

# All initial channels, then up to five voltage-change rows.
python3 query_run_hv.py 125470 --nlines 5 --ask-password

# All initial channels and qualifying changes during the run.
python3 query_run_hv.py 125470 --ask-password

# Initial list and qualifying changes as CSV, optionally restricted to a PSU.
python3 query_run_hv.py 125470 --csv --ask-password > run125470_hv.csv
python3 query_run_hv.py 125470 --psu mu2e-trk-psu7 --ask-password
```

--nlines limits only change rows after the separator; it never truncates the
initial list. Omit it or use0 for all qualifying changes; --limit remains an
alias. --samples is a compatibility alias for --csv. The dotted separator is
a single-field row, including in CSV output. Samples stream through a
server-side cursor without loading the entire run into memory.
Errors exit nonzero; discard incomplete redirected output after failure.

The script reads archived OTS DAQInterface start/stop UTC timestamps over SSH
alias calo-01. It filters PostgreSQL samples to [start,end), including pauses.
No run-number column exists in the HV archive. A run without a stop is rejected.
--metadata accepts a local metadata.txt; --metadata-host selects another SSH
host. --start and --end accept explicit ISO8601 timestamps with a timezone,
but the supplied run label cannot then be independently verified.

Automatic tunneling uses mu2eshift@mu2e-dcs-01.fnal.gov via mu2egateway01.fnal.gov,
with a temporary local loopback port. It targets the database network hostname,
not remote localhost: PostgreSQL rejects dcs_writer from127.0.0.1 but accepts
network address131.225.245.20 for authentication (verified2026-10-21).
--ssh-host and --jump-host override SSH destinations. The tunnel is closed on
normal exit, query failure or interruption. SSH authentication is separate from
PostgreSQL authentication; --ask-password prompts for the database password.
Passwords are never passed as command arguments or printed in error messages.

Use the fully qualified SSH hostname: on this laptop, the short name
`mu2e-dcs-01` fails GSSAPI authentication while `mu2e-dcs-01.fnal.gov` succeeds.
For an older copy of the script, pass
`--ssh-host mu2eshift@mu2e-dcs-01.fnal.gov`.

Database defaults: mu2e-dcs-01.fnal.gov:5434/dcs_archive, role dcs_writer.
PGHOST/PGPORT/PGDATABASE/PGUSER and corresponding CLI options override these.
--host/--port specify the destination as reached from the SSH host. For an
existing manual tunnel or a direct connection, use --no-tunnel, for example:

```bash
python3 query_run_hv.py 125470 --no-tunnel --host 127.0.0.1 --port 15434 --ask-password
```

Transactions are read-only. No database schema, DAQ, configuration, protection,
power or service changes are made. --dry-run resolves run times without a DB
connection/tunnel. --timeout-seconds changes the default120-second server
statement timeout. A protected libpq password file can replace the password
prompt; with an automatic tunnel it must match127.0.0.1 and the dynamic local
port (wildcard port or matching service configuration).

Validation: archived run125470 resolved18:22:08–20:37:04UTC; previous DB checks
found216 voltage streams/18PSUs and1748736 samples. Tunnel reaches database
authentication and closes afterward. Latest mocked-driver checks verify the
four output columns and read-only connection cleanup. Latest tests verify
216initial rows, dotted separator, strict500V boundary, cumulative change
relative to last printed sample, independent channels and --nlines. A live
read-only query of the first minute of run125470 returned all216initial values
and no qualifying changes.
