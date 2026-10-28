# Shared alarm policy

Edit **alarm-policy.json** in this directory to change ROC, environmental,
network and AC-loss alarm settings. This is the sole operational source for
these numeric thresholds, streak counts, polling periods and notification
cooldowns. The checked-in values preserve the previous application defaults.
It contains no credentials, device addresses or PSU-specific wiring.

| Section | Settings | Existing action |
| --- | --- | --- |
| `roc_temperature` | High temperature, consecutive high readings, missing-data timeout, polling, LV-on voltage cutoff, minimum panels with temperatures | Local PSU LV off and notification when live mode is enabled |
| `i2c_environment` | Temperature, humidity, dew-point limit/margin, unsafe/missing streaks, polling and alert cooldowns | Fleet LV off and notifications when live mode is enabled |
| `network` | Polling, connection timeout, connectivity grace period | Local PSU LV off when live mode is enabled |
| `ac_power` | GPIO21 repeated-loss time window | Local PSU LV off after repeated loss edges |

Temperature/humidity alarms use strict `>` comparisons. The environmental dew
alarm uses `>= dew_point_limit_c - dew_point_margin_c`; the defaults therefore
trigger at13°C, not18°C. Missing ROC data uses strict `>` elapsed time, with the
window starting when LV is first observed ON if no valid quorum exists. Network
loss uses `>=` elapsed grace time. Notification cooldowns do not delay shutdown.
GPIO6 AC loss remains immediate; it has no numeric threshold to configure here.

Validate offline from the repository root:

```sh
python3 common/alarm_policy.py
python3 -m unittest discover -s Client/tests -p test_alarm_policy.py -v
```

The loader rejects missing/unknown/duplicate keys, unsupported schema versions,
nonfinite numbers, invalid counts, negative timings and out-of-range humidity.
Counts must be positive integers; the ROC panel minimum is1–512. ROC polling
must be at least20s, other polling/connection/grace/repeat times and LV-on cutoff
must be positive. Cooldowns and dew margin may be zero; humidity is0–100%.
It never substitutes hidden default thresholds for an invalid or missing file.
Checks do not import application services, open hardware or send notifications.
CI runs the policy tests too.

Services locate the policy relative to `common/alarm_policy.py` in their checkout.
`LVHV_ALARM_POLICY=/absolute/path/to/alarm-policy.json` explicitly selects another
complete policy file; this changes the file location, not individual values.
Deployment sets the path to `/home/mu2e/LVHVBox/config/alarm-policy.json` for all
four monitors. Installed flat layouts must supply both `alarm_policy.py` and
an explicit policy path (or the same relative `config/` layout).

Numeric legacy I2C/network environment overrides and the GPIO21 INI/environment
repeat-window override are ignored. ROC numeric CLI options are removed and
rejected. Credentials, endpoints, action mode (`--dry-run`/live), GPIO assignments
and device-control pulse settings retain their existing configuration mechanisms.

[AFFECTS LV/HV OR DETECTOR HARDWARE] Policy values govern automatic power-off.
Running processes keep the policy they loaded at startup. Editing the JSON does
not hot-reload it; restart the affected monitors after reviewing and validating
the change. No power-on, reset or restart is performed by the validator.
Tracked local policy edits are protected by the same deployment guard as other
source changes; commit/push them before a normal GitHub deployment.

Ansible validates the incoming policy and its matching loader directly from
fetched Git objects before stopping services, then validates the checked-out
file before install/activation. It does not maintain another copy of thresholds.
Old releases with neither the policy nor loader remain available for rollback.
