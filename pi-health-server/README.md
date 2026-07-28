# Pi Health Server

This service is separate from the main LV/HV server and is intended to monitor Raspberry Pi health-related signals.

The current monitors watch:

- `GPIO5` for X728 shutdown/reboot requests
- `GPIO6` for AC power status changes
- `GPIO21` for AC fail changes

and can trigger LV shutdown actions:

- `GPIO6` AC loss immediately connects to `lvhv-server` and issues `powerOff`
- `GPIO21` AC loss starts a timer; a second AC loss within the configured window issues `powerOff`

and log:

- AC power loss
- AC power restore
- the raw GPIO level seen at the event
- the event timestamp in local time and UTC
- battery voltage from the X728 fuel gauge
- battery capacity percentage from the X728 fuel gauge
- a read-only HTTP status API for local or remote clients
- an X728 v2.x software-safe-shutdown action

## Assumptions

The service defaults to treating both inputs as:

- `HIGH` = AC power lost
- `LOW` = AC power present

If your X728 wiring or firmware behaves with the opposite polarity, set:

```ini
Environment=PI_HEALTH_GPIO6_ACTIVE_LOW=1
Environment=PI_HEALTH_GPIO21_ACTIVE_LOW=1
```

in the systemd unit.

## Files

- `pi-health-server.py`: GPIO event logger
- `pi-health-actions.ini`: action config for LV shutdown behavior
- `../systemd/pi-health-server.service`: systemd unit

## Power-off action config

The GPIO21 repeat-loss window is configured in `pi-health-actions.ini`:

```ini
[power_actions]
gpio21_repeat_window_seconds = 10.0
lvhv_host = 127.0.0.1
lvhv_port = 12000
lvhv_commands_path = /etc/mu2e-tracker-lvhv-tools/commands.h
lvhv_poweroff_channel = 6
x728_soft_shutdown_line = 26
x728_soft_shutdown_pulse_seconds = 2.0
x728_reboot_pulse_minimum_seconds = 0.2
x728_shutdown_pulse_minimum_seconds = 0.6
systemctl_path = /usr/bin/systemctl
```

The service reads `/etc/pi-health-actions.ini` by default via `PI_HEALTH_ACTION_CONFIG_PATH`.

## HTTP API

The service exposes an HTTP API on port `12002` by default. Status and event
queries are read-only; the soft-shutdown route is the single action endpoint.

- `GET /health`: current AC power state and the last event
- `GET /health`: also includes `battery_voltage_v` and `battery_capacity_pct`
- `GET /health`: also includes per-input states under `ac_inputs`
- `GET /events?limit=20`: recent AC power events
- `POST /soft-shutdown`: pulse the X728 v2.x shutdown input and start a safe
  operating-system shutdown

The shutdown endpoint only accepts loopback clients. Remote clients must use the
existing SSH tunnel. This prevents unauthenticated shutdown requests from the
network even when the read-only status API listens on all interfaces.

Example:

```bash
curl http://localhost:12002/health
curl http://localhost:12002/events?limit=10
curl -X POST http://localhost:12002/soft-shutdown
```

## Runtime requirements

Install `python3-gpiod` and `python3-smbus` on the Raspberry Pi:

```bash
sudo apt-get update
sudo apt-get install -y python3-gpiod python3-smbus
```

## Install

Copy the script somewhere stable, for example:

```bash
sudo install -m 0755 pi-health-server/pi-health-server.py /usr/local/bin/pi-health-server
sudo install -m 0644 pi-health-server/pi-health-actions.ini /etc/pi-health-actions.ini
sudo install -m 0644 systemd/pi-health-server.service /etc/systemd/system/pi-health-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now pi-health-server.service
```

## Logs

By default, events are appended to:

```text
/var/log/pi-health/ac-power-events.log
```

and also sent to the systemd journal:

```bash
journalctl -u pi-health-server.service -f
```

## Client.py commands

`Client/Client.py` can query this service with:

```text
ac_status
ac_events
ac_events 50
soft_shutdown confirm
```

`soft_shutdown confirm` implements Geekworm's X728 v2.0-v2.5 software shutdown:
GPIO26 is driven high for two seconds and then restored low. The X728 responds
on GPIO5; `pi-health-server` interprets that pulse and invokes `systemctl
poweroff`. It also handles the onboard button's reboot and shutdown requests.
X728 v1.2/v1.3 boards use GPIO16 instead of GPIO26, which can be selected in
`pi-health-actions.ini`.

Do not run Geekworm's `x728-pwr.service` at the same time because both services
would attempt to claim GPIO5:

```bash
sudo systemctl disable --now x728-pwr.service
sudo systemctl restart pi-health-server.service
```

If the client is remote, it uses the same SSH gateway flow as the LV/HV connection, but forwards the health HTTP service on port `12002` by default.
