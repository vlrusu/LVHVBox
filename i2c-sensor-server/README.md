# I2C Sensor Server

This service is generic at the server layer and sensor-specific only at the driver layer.

It:

- polls one I2C-attached sensor
- keeps the latest reading plus a recent in-memory history buffer
- exposes a small read-only HTTP API
- can write readings to InfluxDB

Notifications are intentionally handled by a separate `i2c-sensor-alerts` service.

Today the implemented driver is `bme680`. Other PSU boxes can reuse the same service shape and select a different driver later without changing the HTTP/server packaging model.

## Files

- `i2c-sensor-server.py`: generic polling loop and HTTP server
- `i2c-sensor.env`: sample runtime configuration
- `../systemd/i2c-sensor-server.service`: systemd unit

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

## Alerting

Use the separate `i2c-sensor-alerts` service if you want Pushover notifications. It polls this server's `/health` endpoint and applies threshold logic outside the acquisition process.

## Install

```bash
sudo install -m 0755 i2c-sensor-server/i2c-sensor-server.py /usr/local/bin/i2c-sensor-server
sudo install -m 0644 i2c-sensor-server/i2c-sensor.env /etc/mu2e-tracker-i2c-sensor-tools/i2c-sensor.env
sudo install -m 0644 systemd/i2c-sensor-server.service /etc/systemd/system/i2c-sensor-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now i2c-sensor-server.service
```
