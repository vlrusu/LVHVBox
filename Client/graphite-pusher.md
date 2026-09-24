# Graphite collection schedules

`graphite-pusher` uses three independent workers, with two LVHV connections and a separate
RS485 HTTP client:

| Group | Measurements | Default interval |
| --- | --- | --- |
| HV | All 12 HV voltages and currents (`vhv_v`, `ihv_ua`) | 1 second (`--hv-interval`) |
| Slow | V48/I48, V6/I6, board temperature, AC status, and battery health | 20 seconds (`--interval`) |
| RS485 | Four direct FPGA TVS values and calibrated Flow for each discovered panel | 20 seconds (`--rs485-interval`) |

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

Every RS485 cycle fetches the server's cached `/panels` list, then reads these
five values sequentially per panel. It never triggers discovery, recovery, a
firmware operation or a direct UART open. The default server is
`127.0.0.1:12004`; override with `--rs485-host`/`--rs485-port`.
`--rs485-timeout` defaults to 30 seconds to accommodate the CPU reply deadline
and persisted bus holdoff independently of the other workers' network timeout.

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
