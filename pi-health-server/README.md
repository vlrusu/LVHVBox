# Pi Health Server

This service is separate from the main LV/HV server and is intended to monitor Raspberry Pi health-related signals.

The first monitor implemented here watches `GPIO6` for AC power status changes from the Geekworm X728 and logs:

- AC power loss
- AC power restore
- the raw GPIO level seen at the event
- the event timestamp in local time and UTC
- battery voltage from the X728 fuel gauge
- battery capacity percentage from the X728 fuel gauge
- a read-only HTTP status API for local or remote clients

## Assumptions

The service defaults to treating `GPIO6 = HIGH` as "AC power lost" and `GPIO6 = LOW` as "AC power present".

If your X728 wiring or firmware behaves with the opposite polarity, set:

```ini
Environment=PI_HEALTH_GPIO_ACTIVE_LOW=1
```

in the systemd unit.

## Files

- `pi-health-server.py`: GPIO event logger
- `../systemd/pi-health-server.service`: systemd unit

## HTTP API

The service also exposes a small read-only HTTP API on port `12002` by default.

- `GET /health`: current AC power state and the last event
- `GET /health`: also includes `battery_voltage_v` and `battery_capacity_pct`
- `GET /events?limit=20`: recent AC power events

Example:

```bash
curl http://localhost:12002/health
curl http://localhost:12002/events?limit=10
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
```

If the client is remote, it uses the same SSH gateway flow as the LV/HV connection, but forwards the health HTTP service on port `12002` by default.
