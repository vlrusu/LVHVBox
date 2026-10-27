# HV archive without duplicate Graphite output

Set `MU2E_GRAPHITE_HV_ENABLED=0` in the service environment or pass
`--no-graphite-hv` to send only HV voltage/current to PostgreSQL. All other
Graphite telemetry, including HV collector status, LV, board temperature,
Pi-health and RS485 data, continues unchanged. All three collection workers
and their intervals are retained. PostgreSQL must be enabled for this option
(except in dry-run mode); removing the override restores duplicate HV output.
Metric names/channel IDs and PostgreSQL queue behavior are unchanged.

# Graphite collection schedules

`graphite-pusher` uses three independent workers, with three LVHV connections and a separate
RS485 HTTP client:

| Group | Measurements | Default interval |
| --- | --- | --- |
| HV | All 12 HV voltages and currents (`vhv_v`, `ihv_ua`) | 1 second (`--hv-interval`) |
| Slow | V48/I48, V6/I6, board temperature, AC status, and battery health | 20 seconds (`--interval`) |
| RS485 | Four direct FPGA TVS values plus CPU Flow, V5KEY, V2.5KEY and DCDCTEMP for each discovered panel | 20 seconds (`--rs485-interval`) |

Each worker collects and sends its own batch. Slow I2C conversions, health
requests, RS485 timeouts, or Graphite sends in one worker do not block the others.
The LVHV socket is never shared between workers. Existing measurement paths
remain unchanged.

Intervals use a monotonic clock. If a worker takes longer than its interval,
missed slots are skipped; it does not send catch-up bursts or reuse old readings.
The requested interval is a target, not a real-time guarantee. Metric timestamps
remain integer Unix seconds. Use intervals of at least one second to avoid
multiple samples for the same metric and timestamp.

`collector.hv.success` reports success/failure for the HV group. The existing
`collector.success` now reports success/failure for the slow group. A failed
cycle closes that worker's LVHV connection and reconnects on its next cycle;
the other worker continues independently.

To collect all three groups once without sending to Graphite (this still reads
LV/HV and panel hardware):

```sh
graphite-pusher --once --dry-run
```

The service unit sets `--hv-interval 1 --interval 20 --rs485-interval 20` and runs
`/usr/bin/python3`. Deploy the updated script, `RS485Connection.py` Python module
and unit together, reload systemd, and restart `graphite-pusher`. The Ansible
`deploy_graphite_pusher.yml` installs this module into the service interpreter's
module directory and restarts the pusher when it changes. No LVHV server
change is needed. Graphite's storage resolution for the HV series must also
retain one-second samples; faster collection alone does not change existing
Whisper archives.

Run the hardware-independent tests from the repository root:

```sh
python3 -m unittest discover -s Client/tests -v
```

## RS485 panel measurements

When PSU power is ON, each RS485 cycle fetches the server's cached `/panels`
list, then reads these
five values sequentially per panel. It never triggers discovery, recovery, a
firmware operation or a direct UART open. The default server is
`127.0.0.1:12004`; override with `--rs485-host`/`--rs485-port`.
`--rs485-timeout` defaults to 30 seconds to accommodate the CPU reply deadline
and persisted bus holdoff independently of the other workers' network timeout.

Power is checked using all six V6 readbacks only. **All six below 2 V means
OFF; any one at or above 2 V means ON for every discovered panel.** The RS485
worker has its own LVHV connection. Each cycle reads fresh V6 before any RS485
request; during a scan it rechecks before the next parameter when at least five
seconds have elapsed. An in-flight request can still finish or time out before
the next check. Once OFF, remaining reads stop; polling resumes on the next
scheduled cycle that observes ON. No hardware power command is sent.

While OFF, only `collector.rs485.enabled=0` is emitted by this worker; sensor
values and read-success metrics are omitted, not set to zero. While ON,
`collector.rs485.enabled=1` accompanies the normal results. Power transitions
are logged once, without repeating off messages every cycle. Malformed V6,
nonfinite values, the -1 error sentinel, and failed power reads mean unknown:
skip RS485 requests and report a collector failure, never assume OFF. Small
negative ADC offsets above -1 V count as OFF. LV/HV and Pi-health collection
continues independently in either case.

Example prefix: `mu2etrk.lvhv.mu2e-trk-psu8.panels.MN253`.

| Parameter | Graphite suffix | Read path |
| --- | --- | --- |
| ROC_TEMP | `.ROC_TEMP` | FPGA direct |
| ROC_RAIL_1V | `.ROC_RAIL_1V` | FPGA direct |
| ROC_RAIL_1.8V | `.ROC_RAIL_1_8V` | FPGA direct |
| ROC_RAIL_2.5V | `.ROC_RAIL_2_5V` | FPGA direct |
| Flow | `.Flow` | CPU, with existing per-panel calibration applied by the server |

Values are published exactly as returned by the server's `value` field; no
extra conversion or new calibration is applied. Dots in parameter names become
underscores so each parameter stays one Graphite path component. RS485 metric
timestamps are the host time after each successful read, not the start of a
potentially long polling cycle. The four hardware values are separate samples.

An individual failure (including unavailable/stale FPGA data or missing Flow
calibration) logs the error and omits that measurement. Successful readings from
that panel and subsequent panels are retained. There is no immediate retry or
CPU fallback for the FPGA values. The next scheduled cycle attempts them again.
Panels absent from cached discovery are not polled or given fabricated samples.

The RS485 connection identifies as `graphite` for the server's fair queue.
Each variable is one turn; a waiting temperature-monitor or interactive request
gets its turn before Graphite can monopolize further reads. The30-second HTTP
timeout includes queue wait, with a server deadline0.5 seconds shorter. Queue
full/deadline errors omit that sample and are not immediately retried. Deploy
the updated `RS485Connection.py` with the pusher to enable this identification.

Under the PSU prefix, `.collector.rs485.panels` reports the discovered count and
`.collector.rs485.success` is 1 only if at least one panel was present and all
five reads for every panel succeeded. Each panel also has `.collector.success`
for its five reads. An unavailable/incomplete discovery service emits only the
RS485 collector failure status; an empty completed inventory emits count0 and
failure status. LV/HV and Pi-health workers remain independent. Missing or
failing Flow still requires fixing the CPU path even when all FPGA reads work.

[RESTARTS OR SIGNALS PROCESS] [AFFECTS DETECTOR HARDWARE] Deploying/restarting
this pusher enables periodic panel reads on the discovered inventory. Ordering
after `rs485-server.service` does not start or restart that service itself.
Existing Graphite archives/dashboards are not modified by this source change.

## Optional PostgreSQL output (HV only)

Local implementation added 2026-10-02; live database schema and deployment have
not been verified. Enable with `--postgres` or `MU2E_POSTGRES_ENABLED=1`.
The service Python interpreter needs `psycopg2` (on Debian, package
`python3-psycopg2`). Connection settings use libpq's `PGHOST`, `PGPORT`,
`PGDATABASE`, `PGUSER`, `PGSERVICE`, `PGPASSFILE`, and TLS settings such as
`PGSSLMODE`. Keep passwords in a protected libpq password file, not CLI
arguments, source code or deployment logs. Database exception messages are
redacted to the exception class.

Only HV voltage (`vhv_v`) and current (`ihv_ua`) are queued for PostgreSQL.
LV, Pi health, RS485 and collector status continue to Graphite only.

The writer uses the existing `trk_channel` and `trk_value` tables in the
connection's search path. It creates no tables and makes no schema changes.
The channel identity proposed by this implementation is:

| Column | Mapping |
| --- | --- |
| `name` | Full Graphite metric path, including PSU and panel identity |
| `psu` | Metric node (default: short local PSU hostname) |
| `channel` | HV `chN` number (0–11 in the current collector) |
| `unit` | V for `vhv_v`; uA for `ihv_ua` |
| `time` | Original sample Unix timestamp converted to an aware UTC datetime |
| `channel_id` | Matching `trk_channel.id` |
| `value` | Original finite numeric sample |

For example, `mu2etrk.lvhv.mu2e-trk-psu1.channels.ch11.ihv_ua` maps to
PSU `mu2e-trk-psu1`, channel `11`, unit `uA`. Each physical HV channel
has two metadata rows, one for voltage and one for current (24 streams per PSU
with the current 12-channel collector). These naming choices must be checked
against existing database rows before enabling output.

By default, all matching channel rows must already exist. A missing or ambiguous
identity rolls back and drops the entire collected batch. Optional
`--postgres-register-channels` or `MU2E_POSTGRES_REGISTER_CHANNELS=1` creates
missing metadata. This requires an identity/sequence default on `id`, permission
to use that sequence, and INSERT permission on `trk_channel`. Existing metadata
is never overwritten. Registration takes transaction advisory lock `73482901`
to serialize cooperating pusher instances; a UNIQUE constraint on
`(name, psu, channel)` is recommended to protect against other writers. This
implementation expects READ COMMITTED transactions. Cached IDs are refreshed
on connection failure or service restart; do not replace/delete channel rows
while the pusher is running.

Each collected batch is one database transaction. A separate writer thread
with a bounded queue prevents DB delays from blocking collection/Graphite.
Default queue capacity is 120 batches (`--postgres-queue-size`); full queues
drop the newest batch and log it. Connection and statement/lock timeouts are
5 seconds, followed by a 5-second failure backoff. Failed batches are dropped
without retry because a lost commit reply can leave the commit outcome unknown.
Graphite send failures do not suppress PostgreSQL output or fabricate a sensor
failure status. The DB queue is memory-only; process exit/restart can lose
pending samples. Shutdown allows up to 10 seconds for draining. This is
best-effort telemetry, not durable archival or exactly-once delivery.

`--dry-run` prints Graphite lines and sends to neither sink; it still performs
hardware reads. The database driver is loaded only for enabled live DB output.

[READ-ONLY] Before enabling, inspect metadata/defaults/constraints in the target
DB (with connection settings supplied through protected libpq configuration):

```sql
SELECT column_name, column_default, is_identity
FROM information_schema.columns
WHERE table_schema = current_schema() AND table_name = 'trk_channel';
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid IN ('trk_channel'::regclass, 'trk_value'::regclass);
SELECT id, name, psu, channel, unit FROM trk_channel ORDER BY id LIMIT 20;
```

[CHANGES CONFIG] For the exact chosen PSU, configure a systemd drop-in with a
protected EnvironmentFile containing `MU2E_POSTGRES_ENABLED=1` and the libpq
settings. [RESTARTS OR SIGNALS PROCESS] Enabling requires restarting only that
PSU's `graphite-pusher`. Prerequisites are confirmed endpoint, matching channel
identity, DB permissions, installed driver, and registration ID default if used.
Expected effect: continue Graphite and insert subsequent telemetry into the DB.
Rollback: remove the enable setting and restart the same pusher; stored rows
remain. No deployment or restart was performed as part of this local edit.

[READ-ONLY] Verify the exact selected PSU after enabling:

```sql
SELECT c.name, c.psu, c.channel, c.unit, v.time, v.value
FROM trk_value v JOIN trk_channel c ON c.id = v.channel_id
WHERE c.psu = 'mu2e-trk-psu1'
ORDER BY v.time DESC LIMIT 30;
```

Check that timestamps advance and values match that PSU's collected metrics;
inspect its `graphite-pusher` journal for dropped/failed batches. Replace the
example PSU with the actual target. Automated tests mock the driver; a live
PostgreSQL integration check is still required.

Transaction handling follows the [Psycopg connection documentation](https://www.psycopg.org/docs/connection.html).

### User-supplied archive endpoint — 2026-10-02

Connection: host `mu2e-dcs-01`, port `5434`, database `dcs_archive`, user
`dcs_writer`. This was supplied by the user; connectivity, credentials, TLS
policy, schema/search path, channel rows and ID defaults remain unverified.
Configuration examples are `systemd/graphite-pusher-postgres.env.example` and
`systemd/graphite-pusher-postgres.conf.example`. Registration is disabled pending
schema and metadata verification. Enabling should begin on one explicitly chosen
PSU; these examples have not been installed or activated.

Use a root-owned mode-0600 libpq password file at the example PGPASSFILE path for
the current root-run service. Populate its host/port/database/user entry privately;
do not commit it. Confirm the site's TLS policy before enabling the connection.

[READ-ONLY] Inspect the target tables from a host with database access:

```sh
psql -h mu2e-dcs-01 -p 5434 -d dcs_archive -U dcs_writer
```

In psql, run:

```text
\conninfo
SHOW search_path;
\d trk_channel
\d trk_value
SELECT id, name, psu, channel, unit FROM trk_channel ORDER BY id LIMIT 10;
```

These reads resolve compatibility with existing naming/constraints before
inserting any samples. The implementation currently resolves tables through the
connection's search path; if the tables are in a different schema, that must be
configured explicitly before deployment.

### psu0 deployment verified — 2026-10-02

PostgreSQL output and automatic channel registration are active on psu0 only.
Live preflight confirmed the public schema, identity-generated channel IDs and
insert permissions. Verification found 24 HV streams, each advancing at one
sample per second, and fresh Graphite HV output. Only graphite-pusher restarted;
LVHV, RS485, temperature-monitor and Pi-health PIDs stayed unchanged.
Evidence and exact rollback: DRACFirmware/operations/psu0-postgres-hv-20261002/README.md.
At that stage only psu0 had PostgreSQL output enabled; the later fleet rollout
below expanded it to all18.

### Fleet deployment verified — 2026-10-02

PostgreSQL HV output and channel registration are now active on psu0–psu17.
All18 have python3-psycopg2 and the psql command-line client; the database
server remains on mu2e-dcs-01.fnal.gov:5434/dcs_archive. Root-only credentials
and per-service environment/drop-ins are installed. Each PSU contributes24HV
streams, with432total advancing in PostgreSQL and fresh in Graphite. The HV
interval remains1s. Only psu1–17 graphite-pusher processes restarted; psu0 and
other checked service PIDs were preserved.

Required client packages for this deployment are `python3-psycopg2` and
`postgresql-client`. The Python driver is used by the pusher; psql is for manual
queries. Per-host backups, exact deployment evidence and rollback are recorded
in DRACFirmware/operations/postgres-hv-fleet-20261002/README.md.

Key metrics use existing rs485-server transformations, with no exporter conversion: V5KEY and V2.5KEY in V, DCDCTEMP in °C. Graphite leaf V2_5KEY replaces the decimal point. Failed CPU reads produce gaps; direct FPGA reads and other CPU parameters continue.
