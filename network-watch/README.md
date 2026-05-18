# Network Watch

This service runs locally on each PSU box and watches fleet reachability.

It:

- probes configured master PSU hosts over TCP
- decides whether the local box appears isolated from the master control plane
- issues a local LV `powerOff` when the configured isolation condition persists

Default policy:

- probe the configured `NETWORK_WATCH_MASTER_HOSTS`
- connect to port `12000`
- require all configured masters to be reachable, including self if self is listed
- require `3` consecutive failed polls before shutdown
- once isolated, re-send local `powerOff` on every poll until connectivity returns

## Files

- `network-watch.py`: reachability watcher
- `network-watch.env`: master host list and threshold config
- `../systemd/network-watch.service`: systemd unit

## Install

```bash
sudo install -m 0755 network-watch/network-watch.py /usr/local/bin/network-watch
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
ExecStart=/bin/network-watch --dry-run
```
