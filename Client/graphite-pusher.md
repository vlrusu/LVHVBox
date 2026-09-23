# Graphite collection schedules

`graphite-pusher` uses two independent workers and two LVHV connections:

| Group | Measurements | Default interval |
| --- | --- | --- |
| HV | All 12 HV voltages and currents (`vhv_v`, `ihv_ua`) | 1 second (`--hv-interval`) |
| Slow | V48/I48, V6/I6, board temperature, AC status, and battery health | 20 seconds (`--interval`) |

Each worker collects and sends its own batch. Slow I2C conversions, health
requests, or Graphite sends in one worker do not block the other worker.
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

To collect both groups once without sending to Graphite:

```sh
graphite-pusher --once --dry-run
```

The service unit sets `--hv-interval 1 --interval 20`. Deploy the updated script
and unit together, reload systemd, and restart `graphite-pusher`. No LVHV server
change is needed. Graphite's storage resolution for the HV series must also
retain one-second samples; faster collection alone does not change existing
Whisper archives.

Run the hardware-independent tests from the repository root:

```sh
python3 -m unittest discover -s Client/tests -v
```
