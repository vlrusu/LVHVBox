# I2C Sensor Server

This service is generic at the server layer and sensor-specific only at the driver layer.

It:

- polls one I2C-attached sensor
- keeps the latest reading plus a recent in-memory history buffer
- exposes a small read-only HTTP API
- writes readings to the same PostgreSQL archive as HV

Notifications are intentionally handled by a separate `i2c-sensor-alerts` service.

Today the implemented driver is `bme680`. Other PSU boxes can reuse the same service shape and select a different driver later without changing the HTTP/server packaging model.

## Files

- `i2c-sensor-server.py`: generic polling loop and HTTP server
- `i2c-sensor.env`: sample runtime configuration
- `../systemd/i2c-sensor-server.service`: systemd unit
- `bme680/`: bundled upstream sensor driver, license and provenance

## HTTP API

The service listens on port `12003` by default.

- `GET /health`: current service state and latest sample
- `GET /readings?limit=20`: recent samples, newest first
- `GET /samples?limit=20`: alias for `/readings`

Each sample contains:

- `sensor_type`
- `timestamp_local`
- `timestamp_utc`
- `values`
- `source`

## Current driver

Set:

```text
I2C_SENSOR_SERVER_SENSOR_TYPE=bme680
```

for the existing BME680 hardware. The I2C service stays the same; only the driver differs.
When run from source, the collector finds the sibling bundled `bme680` package.
Fleet deployment installs it under `/opt/mu2e-psu/common/i2c-sensor-server/bme680`
and sets that parent path in new sensor environment files. Existing explicit
`I2C_SENSOR_SERVER_SENSOR_REPO` settings remain supported. No separate sensor
driver repository or custom Mu2e Debian package is required.

## Alerting

Use the separate `i2c-sensor-alerts` service if you want Pushover notifications. It polls this server's `/health` endpoint and applies threshold logic outside the acquisition process.

## PostgreSQL archive

The collector uses `mu2e-dcs-01.fnal.gov:5434/dcs_archive`, role `dcs_writer`,
and the existing `public.trk_channel` and `public.trk_value` tables used by HV.
The schema and INSERT permissions were checked live on October 27, 2026 via
PSU7. No new tables, columns, or changes to HV metadata are required.

Each quantity has one `trk_channel` metadata row. Example:
`mu2etrk.environment.mu2e-trk-psu13.i2c4.addr76.bme680.temperature_c`.
The `psu` is the collector hostname; `channel` is the I²C address (118 for
0x76), **not an HV channel**. Bus, address, sensor type and quantity are also
part of the name. `quantity` is the field name below. Existing metadata must
match the expected unit and quantity; conflicts or duplicate identities fail
the batch without changing existing rows.

| Quantity | Unit | Value |
| --- | --- | --- |
| `temperature_c` | C | Sensor temperature |
| `pressure_hpa` | hPa | Sensor pressure |
| `humidity_rh` | %RH | Relative humidity |
| `dew_point_c` | C | Calculated dew point, omitted if unavailable |
| `gas_resistance_ohms` | ohm | Gas resistance, omitted until heater stable |
| `heat_stable` | bool | 0 or 1 |

Values enter `trk_value(time, channel_id, value)` using the original aware UTC
sample timestamp. Null/unavailable values are omitted; nonfinite or mistyped
fields are skipped and counted. No synthetic zero is used for missing data.

PostgreSQL logging and automatic metadata registration default to enabled.
Settings are `I2C_SENSOR_SERVER_POSTGRES_ENABLED`,
`I2C_SENSOR_SERVER_POSTGRES_REGISTER_CHANNELS` (1/0) and
`I2C_SENSOR_SERVER_POSTGRES_QUEUE_SIZE` (positive integer, default 120 batches).
Registration uses the same transaction advisory lock as the HV writer.
Metadata and that sample's values commit in one transaction; IDs are cached
only after commit. Registration can be disabled after provisioning metadata.

Connection settings use `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGPASSFILE` and libpq TLS/password settings. Defaults match HV; the password
file defaults to `/etc/mu2e-tracker-lvhv-tools/postgres.pgpass`. Reuse the
protected HV password file. Never put passwords in source, CLI arguments or
logs. The service needs `python3-psycopg2` and fails startup explicitly if
logging is enabled without the driver.

The bounded worker queue keeps database delays out of sensor polling and HTTP
protection readings. Connect, statement and lock timeouts are 5 seconds. Full
queues drop the newest batch; failed batches drop without retry because a
lost commit reply has an ambiguous outcome. Connection failures clear the
connection/cache; the next batch reconnects after a 5-second backoff.
Delivery is best effort: no disk spool, historical backfill or exactly-once
guarantee; shutdown allows 10 seconds for draining. Database errors expose
only exception classes and do not change sensor health status.

`GET /health` exposes `postgres_enabled`, `postgres_last_success_utc` (sample
time of last committed batch), `postgres_last_error`, `postgres_batches_written`,
`postgres_batches_dropped` and `postgres_fields_skipped`. A fresh sensor
sample alone does not prove a database commit.

The previous database client, settings and dependency have been removed.
Old environment keys are ignored. Existing historical data is not deleted
or imported by this change.

## Deployment boundary

Local source and tests changed October 27, 2026; **not yet activated**.
Read-only PSU13 checks found the collector and HV exporter units absent,
no BME680 repository/driver, no psycopg2, no HV config directory, and no
passwordless sudo. `/dev/i2c-4` exists, but the actual sensor has not been
polled or its address reverified.

[CHANGES CONFIG] [RESTARTS OR SIGNALS PROCESS]
[AFFECTS LV/HV OR DETECTOR HARDWARE] The intended target is only PSU13's
`i2c-sensor-server`. Activation requires administrator access, smbus2,
psycopg2, the BME680 driver, verified bus/address and protected HV database
credentials. Back up existing source/unit/env if present. Install this source,
the provided unit and reviewed environment settings; preserve site settings.
Start/restart only the collector. It reads/configures the environmental sensor;
the separate protection service can react to returned readings. This migration
does not install, enable or restart that protection service or the HV exporter.
Do not deploy a fleet service upgrade to activate this collector alone.

Verify `/health` sensor freshness, advancing PostgreSQL commit timestamps,
no dropped batches, and database readback matching the sensor. Read only:

```sql
SELECT c.name, c.unit, c.quantity, v.time, v.value
FROM public.trk_channel c
CROSS JOIN LATERAL (
  SELECT time, value FROM public.trk_value
  WHERE channel_id = c.id ORDER BY time DESC LIMIT 1
) v
WHERE c.psu = 'mu2e-trk-psu13'
  AND c.name LIKE 'mu2etrk.environment.mu2e-trk-psu13.%'
ORDER BY c.name;
```

Rollback: stop this collector and restore its backed-up files/state, or
disable its PostgreSQL sink and restart it to retain HTTP-only monitoring.
New metadata and stored readings remain; do not delete archive rows as part
of rollback. Coordinate collector downtime with existing protection monitoring.

## Tests

[READ-ONLY] Offline, with fake sensor and database transports:

```sh
python3 -m unittest discover -s i2c-sensor-server/tests -v
```
