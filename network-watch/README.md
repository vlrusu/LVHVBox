# Network Watch

This service runs locally on each PSU box and watches fleet reachability.

It:

- probes configured master PSU hosts over TCP
- decides whether the local box appears isolated from the master control plane
- issues a local LV `powerOff` when the configured isolation condition persists

Default policy:

- probe the configured `NETWORK_WATCH_MASTER_ENDPOINTS`
- fall back to `NETWORK_WATCH_MASTER_HOSTS` plus `NETWORK_WATCH_REMOTE_PORT` for older env files
- require all configured master endpoints to be reachable
- probe `NETWORK_WATCH_GATEWAY_ENDPOINTS` in order: try gateway01 first, then gateway02 only if gateway01 fails; the gateway check fails only when both fail
- wait `network.grace_period_seconds` (default1800) seconds (30 minutes) of continuous detected connectivity loss before shutdown
- once isolated, re-send local `powerOff` on every poll until connectivity returns

The grace timer starts at the first failed poll and uses monotonic elapsed time.
All master checks and at least one gateway becoming reachable resets it. With the default 30-second polling
period and connection timeouts, shutdown happens on the first failed poll at or
after 30 minutes; counting polls does not determine the delay. Restarting the
watcher starts a fresh grace period. Recovery clears the shutdown latch and does
not power the station back on. The former `NETWORK_WATCH_FAILURE_STREAK_TRIGGER`
setting is replaced by `network.grace_period_seconds` in the shared alarm policy.

Endpoint entries use `host:port`, for example:

```text
NETWORK_WATCH_MASTER_ENDPOINTS=mu2e-trk-psu13.fnal.gov:12000
NETWORK_WATCH_GATEWAY_ENDPOINTS=mu2egateway01.fnal.gov:22,mu2egateway02.fnal.gov:22
```

Gateway alternatives are separate from the required master endpoints: do not
also place gateway01 in `NETWORK_WATCH_MASTER_ENDPOINTS`, which would require
it independently of the fallback. An empty `NETWORK_WATCH_GATEWAY_ENDPOINTS`
retains the master-only behavior for older configurations. A successful fallback
is healthy and clears any outage timer; losing PSU13 still counts as a failure.

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

## Shared alarm policy

Polling period, connection timeout and grace period are loaded from the `network`
section of [`../config/alarm-policy.json`](../config/alarm-policy.json). The former
`NETWORK_WATCH_PERIOD_S`, `NETWORK_WATCH_CONNECT_TIMEOUT_S` and
`NETWORK_WATCH_GRACE_PERIOD_S` overrides are ignored. Endpoint groups, local LVHV
connection settings and `--dry-run` remain separate. Restart after policy changes.
