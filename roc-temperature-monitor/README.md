# ROC temperature monitor

One `roc-temperature-monitor.service` per PSU. The shipped unit explicitly passes
`--enable-power-off`: qualifying alarms shut down all local LV outputs and send
Pushover notifications. Fleet live shutdown was authorized on 2026-09-27.
Running the Python CLI without a mode flag still defaults to alert-only dry run.

Every 60 seconds the monitor:

1. Reads all six `readMonV6` outputs through the local LVHV server (port 12000).
   **The PSU is OFF only if all six V6 readings are below 2 V. Any one
   reading at or above 2 V means the entire PSU is ON**, per the user's
   2026-09-26 instruction. Only the 6 V readback controls monitoring; the 48 V
   readback is not used. The cutoff is configured by `roc_temperature.power_on_min_v` in the shared alarm policy. Small
   negative ADC offsets near zero count as off; the server's -1 error sentinel,
   malformed replies, NaN and timeouts mean **unknown**, not off. Unknown power
   is logged and suppresses action until a fresh valid power read; retained
   missing-data timers continue to age.
2. Requests fresh FPGA-direct `ROC_TEMP` from the local RS485 server (12004) for
   every discovered panel whenever the PSU is ON. No UART/GPIO access, address scans, or CPU fallback.
3. Raises a per-panel alarm for **three consecutive successful readings strictly
   above 36 C**, or one PSU-wide coverage alarm for **more than 180 seconds without
   a cycle returning valid temperatures from at least two distinct discovered panels**. A failed
   sample or value at/below threshold breaks the hot streak. Any valid sample
   counts toward that cycle’s two-panel minimum. A cycle with at least two
   valid temperatures clears the PSU-wide missing-data condition. The initial coverage window starts
   when PSU power is first observed ON, including when discovery is empty.
4. Rechecks power before acting. Live mode sends local `powerOff(channel 6)`,
   verifies all six V6 outputs are below 2 V, and notifies both recipients of the
   reason and result. Failed or unverified shutdown is logged and retried while
   the alarm remains active. With `--dry-run`, it sends real notifications but
   does not send a power command. An OFF PSU resets
   all panel timers and alarms. Individual low channels do not suppress monitoring
   while any of the six channels is ON.

Simultaneous alarms are grouped into messages. Successful alerts are sent once
per incident/recipient, with failed deliveries
retried on the next cycle. A cool reading or observed power-off rearms a hot
alert; a cycle with at least two valid temperatures rearms the coverage alert. There are no periodic
reminders. Journald still records every sample, failed read and active alarm.
Timers, streaks and delivered-recipient hashes survive a service restart on the
same boot with the same policy. Changing dry-run/live mode preserves observations
and timers but clears delivery latches, so an earlier dry-run alert cannot hide
a real shutdown notification. Older state without a mode field is treated as
dry-run state. A reboot or changed policy starts a new window.

Reads are serial and identify as `temperature-monitor` in the RS485 fair queue.
Each HTTP read allows up to30 seconds including queue wait, capped by the
remaining cycle budget; the server deadline is0.5 seconds shorter. Cached
discovery requests retain an8-second maximum. HTTP 409 (bus busy, no request sent) is retried for up to two
seconds. Other failures are not immediately retried. A 45-second read budget
keeps normal cycles near one minute; read order rotates for fairness during an
outage. Panels deferred by the budget count as failed samples. Alarms are
evaluated at the end of the cycle, so missing-data notification happens on the
first completed check after 180 seconds, not at an exact 180-second deadline.
Slow notification delivery can extend a cycle; overruns are logged and do not
cause a burst of catch-up polls.

## Discovery is the only panel source

Every cycle fetches the RS485 server's cached `/panels` result. Only addresses
from a completed discovery are monitored; there is no MIDAS roster or
`panels.json` configuration. New discovered panels get a fresh observation
window. Panels removed by a later completed discovery are removed from all
monitor state and alert latches. An empty completed discovery means no panels
to monitor, even if PSU power is ON.

A missing individual panel does not trigger a protection alert while at least
two other discovered panels return valid temperatures. Fewer than two for more
than three minutes produces one PSU-wide coverage alarm, even with an empty
discovery list. The per-panel over-temperature rule remains unchanged. A failed or incomplete `/panels` request
retains the last successfully discovered set and logs the error; it does not
silently erase missing-panel timers. On first startup with no successful
inventory, the monitor invents no panels but still tracks insufficient coverage
while power is ON. Persisted state
contains only discovery-derived panels; the old roster state is not restored.

The monitor never triggers a UART scan. All-channel LV `powerOn` now notifies RS485 to rediscover after a 5-second boot
delay. Individual-channel commands do not. If a notification was missed while
RS485 was unavailable, perform a fresh RS485 discovery after power is restored. The
monitor adopts that completed result on its next cycle.

## Configuration

Thresholds, consecutive-reading count, missing-data timeout, polling interval,
power cutoff and minimum panel count come from [`../config/alarm-policy.json`](../config/alarm-policy.json).
The former numeric CLI options (`--threshold`, `--high-count`, `--missing-seconds`,
`--interval`, `--power-cutoff`) have been removed; stale invocations fail argument
validation before any power action. `--commands` and `--state` remain supported.
Use a systemd ExecStart override for a different policy, with exactly one mode
flag: `--enable-power-off` for protection or `--dry-run` for alert-only operation.
The current unit cannot inherit live shutdown from a credentials environment
file: only the explicit CLI option `--enable-power-off` enables it, mutually
exclusive with `--dry-run`.

Pushover uses the existing PSU13 credentials in a dedicated root-readable
`/etc/roc-temperature-monitor/pushover.env`. Supported keys:
`I2C_SENSOR_ALERTS_PUSHOVER_API_TOKEN`, `I2C_SENSOR_ALERTS_PUSHOVER_USER_KEY`
(comma-separated recipients), or their `ROC_MONITOR_*` equivalents. systemd
loads this file before dropping privileges to `mu2e`. Never commit credentials.
No test/startup notification is sent automatically.

## Deployment

[NETWORK OR FLEET-WIDE CHANGE] [RESTARTS OR SIGNALS PROCESS]
The Ansible playbook installs and enables **only this monitor service**. It copies
the controller's source files; no Git pull, dependency installation,
LVHV/RS485 restart or firmware change. Enabling live mode permits the monitor
to send power-off if an alarm is already active or becomes active. It reads only the two
Pushover settings from PSU13 using `no_log`, then installs them mode 0600.
It defaults to all 18 PSUs, serially and stopping on failure. Both existing PSU13 destinations are selected by default, as
authorized on 2026-09-25 (`monitor_pushover_recipient_indexes: [0, 1]`).
Override that list explicitly if recipients change. Existing LVHV and RS485
services must be active.

From `RPiFermilab/ansible-lvhv`, preview a PSU13 canary:

```bash
ansible-playbook -i inventory.ini ../../LVHVBox/roc-temperature-monitor/deploy.yml \
  -e lvhvbox_source="$PWD/../../LVHVBox" --limit psu13 --check --diff
```

Run the same command without `--check --diff` to deploy. Remove `--limit psu13`
for the 18-host rollout. Real protection and incident notifications begin once enabled.
The deployment defaults to `monitor_power_off_enabled: true`; explicitly pass
`-e monitor_power_off_enabled=false` to deploy alert-only dry run.
Preserve source/unit backups. Old installed `panels.json` files are archived as
`panels.json.pre-discovery` for rollback only and are never read by this version. Rollback: stop and disable only
`roc-temperature-monitor.service`; this does not send power commands. Restore
its backed-up files before restarting if reverting an update.

[READ-ONLY] Follow monitoring and notification failures:

```bash
ssh psu17 'sudo journalctl -u roc-temperature-monitor.service -f'
```

## Live shutdown

[AFFECTS LV/HV OR DETECTOR HARDWARE] Live mode requires replacing `--dry-run`
with `--enable-power-off`. It sends **only local** `powerOff` channel 6, which
uses the existing LVHV server's all-LV-output/global-enable shutdown; it does not
ramp HV DACs or turn power back on. It checks the command reply and reads V6
again to verify the result. Live shutdown is enabled in the shipped unit and deployment following the
2026-09-27 authorization. Restarting the monitor alone does not cycle LVHV or
RS485; an already-qualified alarm can cause shutdown on its first cycle.

Offline validation (fake hardware/Pushover, local loopback protocol fixture):

```bash
python3 -m unittest discover -s roc-temperature-monitor/tests -v
```

## Startup discovery warnings

The RS485 server separately maintains persistent discovery history and sends
notification-only warnings for previously discovered panels missing on a new
powered startup scan. These do not enter this monitor's protection/alarm path
and can never request power-off. See `../rs485-server/README.md`.
