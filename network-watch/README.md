# Network Watch

This service runs locally on each PSU box and watches fleet reachability.

It:

- probes configured master PSU hosts over TCP
- decides whether the local box appears isolated from the master control plane
- issues a local LV `powerOff` when the configured isolation condition persists

Default policy:

- probe the configured `NETWORK_WATCH_MASTER_ENDPOINTS`
- fall back to `NETWORK_WATCH_MASTER_HOSTS` plus `NETWORK_WATCH_REMOTE_PORT` for older env files
- require all configured endpoints to be reachable
- wait `NETWORK_WATCH_GRACE_PERIOD_S=1800.0` seconds (30 minutes) of continuous detected connectivity loss before shutdown
- once isolated, re-send local `powerOff` on every poll until connectivity returns

The grace timer starts at the first failed poll and uses monotonic elapsed time.
All endpoints becoming reachable resets it. With the default 30-second polling
period and connection timeouts, shutdown happens on the first failed poll at or
after 30 minutes; counting polls does not determine the delay. Restarting the
watcher starts a fresh grace period. Recovery clears the shutdown latch and does
not power the station back on. The former `NETWORK_WATCH_FAILURE_STREAK_TRIGGER`
setting is replaced by `NETWORK_WATCH_GRACE_PERIOD_S`.

Endpoint entries use `host:port`, for example:

```text
NETWORK_WATCH_MASTER_ENDPOINTS=mu2e-trk-psu13.fnal.gov:12000,mu2egateway01.fnal.gov:22
```

## Files

- `network-watch.py`: reachability watcher
- `network-watch.env`: master host list and threshold config
- `../systemd/network-watch.service`: systemd unit

## Install

```bash
sudo install -m 0755 network-watch/network-watch.py /usr/bin/network-watch
sudo install -m 0644 network-watch/network-watch.env /etc/mu2e-tracker-network-watch/network-watch.env
sudo install -m 0644 systemd/network-watch.service /etc/systemd/system/network-watch.service
sudo systemctl daemon-reload
sudo systemctl enable --now network-watch.service
```

## Dry Run

To test the logic without actually powering off LV, start it with:

```bash
network-watch --dry-run
```

Under `systemd`, use:

```bash
ExecStart=/usr/bin/network-watch --dry-run
```
