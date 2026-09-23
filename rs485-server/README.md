# RS485 telemetry

All hardware-side RS485 code and data live in this directory:

| File | Responsibility |
| --- | --- |
| `rs485.py` | Reusable `RS485` class: configuration, protocol, UART/GPIO ownership, reads, conversions and calibration |
| `rs485_server.py` | HTTP interface using one `RS485` instance for the server lifetime |
| `com_v2.py` | Thin standalone CLI using the same class |
| `transformations.json` | All 45 named telemetry rules |
| `panel_calibrations.csv` | Flow calibration by panel |
| `tests/` | Protocol, class, ownership, HTTP and client tests |

The remote `Client/Client.py` uses `Client/RS485Connection.py` over HTTP/SSH. It
has no serial/GPIO or transformation dependency. The server does not import
anything from `Client`. The previous hardware scripts and data in `Client`
have been replaced by this directory. Legacy serial protocol is not supported.

## Shared class

```python
from rs485 import RS485

with RS485() as device:
    result = device.read(253, 'ROC_TEMP')
    print(result['value'])
    print(device.read(253, 'ILP_PRESSURE')['formatted'])
```

Constructing `RS485()` loads configuration without opening hardware.
`parameters()` lists supported names and `preview(address, names)` describes
requests without touching the bus. Entering the context acquires the process
lock, UART and GPIO; exiting releases all three. The same instance can perform
many reads. `read()` requires an open context and returns raw and converted
values, formatting, unit metadata, completion time, and command IDs.

Defaults: `/dev/ttyAMA0`, 38400 baud/8N1, `/dev/gpiochip0`, GPIO24 active-high DE,
6-second response timeout. Constructor keywords `port`, `gpiochip`, `dir_pin`,
`timeout`, `debug`, `rules_path` and `calibrations_path` customize these.
Data paths default beside `rs485.py`, independent of the working directory.
Python 3, pyserial and the gpiod **v2** bindings are required on the Pi.

## Server

From the checkout root:

[READ-ONLY] Validate configuration without opening hardware or a network port:

```sh
python3 rs485-server/rs485_server.py --check-config
```

[AFFECTS LV/HV OR DETECTOR HARDWARE] Run the server on the PSU Pi:

```sh
python3 rs485-server/rs485_server.py
```

The server owns the UART and GPIO continuously, including while idle. Startup
sets DE to receive and opens the UART; telemetry is transmitted only on request.
Confirm v2 FPGA/CPU firmware, the PSU/panel mapping and exclusive access first.
Sensor firmware may configure sensors as part of telemetry reads. There are no
power, reset, firmware, register-write or arbitrary-command HTTP endpoints.

Ctrl-C/SIGTERM stops accepting requests, finishes active reads, and then releases
the UART/GPIO. It cannot undo sensor setup already performed by firmware.
`--serial-port`, `--gpiochip`, `--dir-pin`, `--timeout`, `--rules` and
`--calibrations` override defaults; `--debug` logs raw TX/RX frames.

## Standalone CLI

The server must be stopped before direct CLI use. Both use the same process
lock and GPIO reservation; a competing owner fails without sending a request.
Use the same account and temporary directory for both programs. Do not delete
`/tmp/lvhv-rs485-v2-*.json`: it preserves transaction IDs and pending response
windows, including across restarts and compatibility with earlier v2 clients.
Other programs ignoring the advisory lock must also be stopped.

[RESTARTS OR SIGNALS PROCESS] For an installed systemd service:

```sh
sudo systemctl stop rs485-server.service
```

[AFFECTS LV/HV OR DETECTOR HARDWARE] Then run direct reads on that Pi:

```sh
python3 rs485-server/com_v2.py 253 --name DBG
python3 rs485-server/com_v2.py 253 --name ILP_PRESSURE
python3 rs485-server/com_v2.py 253
```

Omitting `--name` reads every transformation in order. The CLI retains `--panel`,
`--calibrations`, `--rules`, `--port`, `--gpiochip`, `--dir-pin`, `--timeout` and
`--debug`. Timeout/UART failure stops the scan; ROC status/conversion errors
are reported without inventing values. There are no automatic retries.

[READ-ONLY] Preview requests without acquiring hardware; works with server active:

```sh
python3 rs485-server/com_v2.py 253 --name ILP_PRESSURE --dry-run
```

[RESTARTS OR SIGNALS PROCESS] Resume a previously running service when finished:

```sh
sudo systemctl start rs485-server.service
```

## Remote Client.py

From the checkout root on the laptop (or use `localhost` on the Pi):

```sh
python3 Client/Client.py psu8 -c rs485_list
python3 Client/Client.py psu8 -c 'rs485_read MN253 ROC_TEMP'
python3 Client/Client.py psu8 -c 'rs485_read 253 DBG ILP_TEMP ILP_PRESSURE Flow'
python3 Client/Client.py psu8
```

The interactive prompt accepts these commands, `rs485_status`, and existing
LV/HV commands. RS485-only use does not need `lvhv-server` or its opcode header.
Use `--gateway mu2etrk@mu2egateway01.fnal.gov` if required by your SSH setup.
`--rs485-local-port` and `--rs485-remote-port` default to 12004;
`--rs485-timeout` defaults to 30 seconds. Increase this when increasing serial
timeout; allow for pending holdoff and two pressure words. One-shot RS485
failures return exit1 and stop that host's command list.
Addresses are ROC/MN addresses 0..511, not LV/HV channels, slots or PSU numbers.

## HTTP

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Service status and busy flag, not proof of ROC communication |
| `GET /parameters` | Names, command IDs, formats and units; no bus traffic |
| `GET /read?address=253&name=ROC_TEMP` | One fresh named measurement |

Bind defaults to `127.0.0.1:12004`. The unauthenticated endpoint is intended
for loopback access through the client's SSH tunnel. Rules are trusted local
configuration loaded at startup; callers cannot submit expressions/command IDs.

Reads are serialized by the class; concurrent attempts return HTTP409 without
sending or queuing. The process retains UART ownership through success and
failure. Each subsequent transaction honors any pending response holdoff.
Flow requires the panel's A0 calibration. Pressure holds the lock across both
words and returns no value if either fails; firmware acquisitions are separate,
so it has `atomic: false`. ROC errors return502, timeouts504, unavailable I/O503,
and bad requests400. Errors have an `error` string and no measurement.
Responses use `Cache-Control: no-store`.

## Optional systemd service

`systemd/rs485-server.service` runs this directory from `/home/mu2e/LVHVBox`
as `mu2e`. The account needs UART/GPIO access and ownership of its transaction
file. Adjust paths/user for other installations. Temporary testing does not
enable this service.

[RESTARTS OR SIGNALS PROCESS] After deploying the source/data and dependencies
to the intended Pi, with the UART prerequisites above satisfied:

```sh
sudo install -m 644 systemd/rs485-server.service /etc/systemd/system/rs485-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now rs485-server.service
```

Verify service status, `rs485_status`, and an explicitly mapped telemetry read.
Reverse activation with `sudo systemctl disable --now rs485-server.service`.
Do not enable `PrivateTmp`; server and CLI must share the transaction file.
Stop timeout must cover the configured response window and pending holdoff.
No existing LV/HV service needs restarting.

## Offline tests

```sh
python3 -m unittest discover -s rs485-server/tests
```

Tests use simulated hardware and a loopback HTTP server. They cover all45
transformations, real Client.py CLI, exclusive ownership even when idle,
UART reuse across reads, timeout holdoff without reopening, cleanup, concurrent
request rejection, and failed pressure words.
