# I2C Sensor Alerts

This service is separate from `i2c-sensor-server` and is responsible only for notifications.

It:

- polls `i2c-sensor-server` over HTTP
- applies threshold and no-data rules
- sends Pushover notifications
- issues `powerOff` LV shutdown across the configured PSU fleet when an alert condition is triggered

The default alert polling period is `30` seconds.

Temperature, humidity, and dew-point shutdown conditions require `3` consecutive unsafe polls by default.

No-data shutdown uses a separate default trigger of `5` consecutive no-fresh-data polls.

Shutdown enforcement is latched per condition and re-sent on every alert poll until the condition returns to safe.

The sensor server remains responsible for:

- I2C polling
- sample history
- HTTP API
- InfluxDB writes

By default the alert service targets:

- `mu2e-trk-psu0` through `mu2e-trk-psu17`
- port `12000`
- LV `powerOff` channel `6` on each host

## Files

- `i2c-sensor-alerts.py`: notifier loop
- `i2c-sensor-alerts.env`: alert thresholds and Pushover config
- `../systemd/i2c-sensor-alerts.service`: systemd unit

## Install

```bash
sudo install -m 0755 i2c-sensor-alerts/i2c-sensor-alerts.py /usr/bin/i2c-sensor-alerts
sudo install -m 0644 i2c-sensor-alerts/i2c-sensor-alerts.env /etc/mu2e-tracker-i2c-sensor-alerts/i2c-sensor-alerts.env
sudo install -m 0644 systemd/i2c-sensor-alerts.service /etc/systemd/system/i2c-sensor-alerts.service
sudo systemctl daemon-reload
sudo systemctl enable --now i2c-sensor-alerts.service
```

## Dry Run

To test thresholds and fleet shutdown logic without actually sending `powerOff` or Pushover:

```bash
i2c-sensor-alerts --dry-run
```

Under `systemd`, use:

```bash
ExecStart=/usr/bin/i2c-sensor-alerts --dry-run
```
