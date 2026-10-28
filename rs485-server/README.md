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
has no serial/GPIO or transformation dependency. The server's LVHV power-state
reader uses the shared `common/lvhv_protocol.py` codec; serial/GPIO code remains
in this directory. The previous hardware scripts and data in `Client` have been
replaced by this directory. Legacy serial protocol is not supported.

The power-state reader finds the sibling `common` directory when run from source.
For installation, put `lvhv_protocol.py` and `lvhv_protocol_generated.py` on the
service interpreter's module path (the source deployment role already does this).
Each request reads V6 for all six channels using a fresh connection, with the
existing timeout including connection time, at most eight reply blocks and
64 elements per block. Six finite floats greater than -1 are still required;
small negative ADC offsets remain valid and any value at least 2 V means powered.
Invalid/truncated replies remain unknown power, preserving the last discovery
inventory and pending notifications. Requests are never replayed by the transport.
The ROC RS485 serial packet codec remains separate from the LVHV TCP codec.

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

On Linux, transmit completion polls `TIOCSERGETLSR` for `TIOCSER_TEMT` before
lowering GPIO24. This waits for the output queue and physical UART transmitter
to empty, avoiding millisecond-scale `tcdrain()` wake-up delay that can overlap
the FPGA's 1 ms direct reply. Unsupported UART drivers warn and fall back to
`tcdrain()`; fast replies may fail on those drivers. This is not a real-time
scheduling guarantee. PSU0/MN269 was verified with the hardware-empty method
after reproducing a lost reply with `tcdrain()` on 2026-09-23.

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
python3 Client/Client.py psu8 -c 'rs485_read MN253'
python3 Client/Client.py psu8 -c 'rs485_read MN253 ROC_TEMP'
python3 Client/Client.py psu8 -c 'rs485_read 253 DBG ILP_TEMP ILP_PRESSURE Flow'
python3 Client/Client.py psu8
```

The interactive prompt accepts these commands, `rs485_status`, and existing
LV/HV commands. RS485-only use does not need `lvhv-server` or its opcode header.
Omit variable names to discover and read every variable advertised by the server,
in the server's order. Supplying names reads only those variables. Reads remain
sequential and stop on the first error; earlier successful values stay printed.
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

HTTP reads use a bounded fair queue (see below). The direct in-process class API
without a queue request context still reports busy immediately. The process retains UART ownership through success and
failure. Each subsequent transaction honors any pending response holdoff.
Flow requires the panel's A0 calibration. Pressure holds the lock across both
words and returns no value if either fails; firmware acquisitions are separate,
so it has `atomic: false`. ROC errors return502, timeouts504, unavailable I/O503,
and bad requests400. Errors have an `error` string and no measurement.
Responses use `Cache-Control: no-store`.

### Fair request queue

The server takes round-robin turns among `temperature-monitor`, `graphite`,
`interactive`, and `discovery`. A turn is one variable read or control exchange;
both words of a pressure measurement stay together. Discovery takes one address
probe per turn. A lone client runs continuously without waiting for absent clients.
The active transaction always finishes; the queue does not shorten the existing
six-second response timeout or bypass the late-response holdoff.

At most two requests per client class and eight total can wait, in addition to
one active transaction. Client classes are cooperative scheduling labels, not
authentication. Requests within a class are FIFO. Updated Graphite and monitor
clients send `X-RS485-Client`; ordinary/older clients default to `interactive`.
Deploy the updated `RS485Connection.py` and both collectors along with the server
so they receive separate turns. `fair_queue.py` is required by the shared RS485
class, including direct CLI use.

`X-RS485-Timeout` supplies the remaining server budget (0–120 seconds, default30).
Updated clients leave 0.5 seconds before their HTTP timeout. The server reserves
time for a complete exchange, paired words when needed, and persisted holdoff.
Requests expire before starting another queued turn, or are cancelled if
their waiting HTTP connection closes. Once transmission starts, the exchange
finishes safely, including when its client disconnects; recovery activation is
never automatically retried. Shutdown cancels waiting work and drains the active
transaction before releasing the UART. No new reads accumulate after expiry.

HTTP429 means queue full, HTTP408 means deadline/cancellation before the next
transaction, HTTP503 means stopping, and HTTP409 covers a concurrent discovery
or access outside the queue. `GET /health` bypasses the UART queue and exposes
`queue.active_client`, pending counts/limits, completed turns, expired/cancelled
requests, and rejected admissions. Cached inventory and parameter reads also
bypass the UART queue.

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


## Manual golden-image recovery

Requires the new ROC FPGA recovery HDL. No automatic recovery occurs on startup,
CPU absence, telemetry failure, or timeout. In Client, `rs485_recovery_status MN253`
reads the FPGA recovery status without CPU code.

**[FLASHES FIRMWARE / AFFECTS DAQ]** The explicit command
`rs485_recover_golden MN253` activates SPI image 0 on that one panel. Finish any
SPI programming and stop the affected DAQ first. The valid running FPGA must
contain the recovery handler, and the golden image must restore the CPU boot
path. An acceptance ACK is not verification that programming/boot succeeded.
The client reports `boot_verified: false`. Verify firmware identity/CPU response
separately; a lost ACK means an unknown outcome, and is never automatically retried.

The server endpoint is POST `/recover-golden` with Content-Type
`application/json` and `{"address":253,"action":"activate-golden"}`.
There is no activation GET route or arbitrary image selection. Read-only status
is GET `/recovery-status?address=253`. Both share the existing bus lock.
Keep the default loopback listener and access remotely through the SSH tunnel.

For direct UART use after stopping the server, `com_v2.py 253 --recover-golden`
performs the same manual action; `--dry-run` previews it with no hardware access.
`com_v2.py 253 --recovery-status` only reads status. Old FPGA images ignore the new
packet types and time out. No automatic fallback to a CPU command is attempted.


## FPGA panel identity

`rs485_panel_id MN253` in Client reads the cached, validated NVM panel ID directly
from the FPGA, without ROC CPU software. Example output:
`MN253 panel ID: 253 (FPGA cached NVM)`.

The read-only HTTP endpoint is GET `/panel-id?address=253`. The direct UART CLI
is `com_v2.py 253 --panel-id` (stop the server first to release the UART);
`--dry-run` prints the frame without hardware access. It sends type03/command02
with an empty payload and expects type04/status0 plus the 16-bit panel ID.
This differs from the existing CPU-handled telemetry variable `ID`.

Only the addressed panel with a valid cached NVM identity replies. Old firmware
or an absent panel times out. No recovery/activation is requested. The query uses
the existing host timeout and a separate 1 ms FPGA turnaround at 50 MHz; automatic scanning is not
implemented by this command.

## Direct FPGA temperature and rails

With FPGA firmware implementing the direct TVS extension, the read-only Client
command `rs485_direct_read MN253` reads ROC_RAIL_1V, ROC_RAIL_1.8V,
ROC_RAIL_2.5V and ROC_TEMP without the CPU. Select one or more with, for example,
`rs485_direct_read MN253 ROC_TEMP ROC_RAIL_1V`. The existing `rs485_read` and
CPU implementation remain available.

GET `/direct-read?address=253&name=ROC_TEMP` uses type03 request/type04 response,
empty payload and commands03/04/05/06 respectively for the three rails and
temperature. Responses use the existing transformations; `direct_command`
metadata is separate from the original `cmdid`. `/parameters` advertises this
metadata. Returned results identify `source: "FPGA TVS"` and the direct command.
A direct TVS read performs no CPU fallback, activation or discovery scan.

The FPGA caches samples independently of the CPU RAM read port. Samples not yet
acquired or older than one second at 50 MHz return status7, surfaced as an HTTP
502 error rather than a measurement. Samples are latched on request acceptance;
the four reads are sequential, not a simultaneous sample. Fabric clocks, TVS
acquisition and a validated NVM panel identity must be operational. Old firmware
may return unsupported or time out. Existing UART locking, timeout and holdoff
remain in effect; no automatic retries are added.

Direct UART CLI, with the service stopped: `python3 com_v2.py 253 --direct`
or `python3 com_v2.py 253 --direct ROC_TEMP`. Adding `--dry-run` only previews
frames and needs no Pi hardware libraries. Implementation and tests are offline;
the new FPGA and host software still need to be built/deployed.

The direct FPGA interface now uses a separate 1 ms response turnaround at
50 MHz (`DIRECT_TURNAROUND_CLKS=50000`), including panel ID, TVS and recovery
responses. The legacy CPU delay remains unchanged. Expected direct read time is
about 8–11 ms plus host/network overhead. Verify Pi driver release timing on the
board after compilation/deployment; this is an offline timing change.

## Fast panel discovery

On service startup, the server scans addresses **0 through 300 inclusive** once
using the read-only FPGA panel-ID request (type03/command02). Use firmware with
the 1 ms direct turnaround on every connected panel before enabling this scan.
`--no-discovery` skips the startup scan. `--check-config` never scans or opens
the UART. Startup discovery finishes before the HTTP server handles requests.

In Client:

```text
rs485_panels
rs485_discover
rs485_discover 250 300
```

`rs485_panels` displays the most recent completed scan without bus traffic.
`rs485_discover` rescans 0..300, or an inclusive range supplied as integers or
MN identifiers (maximum address 511). The completed scan replaces the in-memory
inventory; a partial-range scan describes only that range. The current inventory
is separate from persistent discovery history described below. No power or recovery action is triggered.

Discovery waits 50 ms after transmitting each request. A missing reply retains
a 5 ms guard before another transaction can start. The longer write/crash
reservation is shortened only after the request has fully left the UART. An
outstanding ordinary request's holdoff is honored before starting discovery.
Normal CPU reads, individual panel-ID reads and recovery requests retain their
existing timeout/holdoff. There is no CPU fallback and no automatic retry.

A mostly empty 0..300 range should take roughly 17–20 seconds on PSU0, including
transmission and guard time; OS scheduling and any prior pending request add
latency; approximately17s was observed during the September26 deployments.
Discovery yields the bus between addresses, so competing reads can lengthen it.
Only one discovery runs at a time. Cached inventory is replaced only when every
probe completes; deadline/cancellation or a UART write/drain failure aborts instead of treating remaining panels
as absent; the previous completed inventory remains available with its timestamp.

HTTP GET `/discover` (or `/discover?start=0&end=300`) returns found addresses,
panel names, no-response addresses, protocol errors, elapsed time and timestamp.
GET `/panels` returns that cached snapshot, or `scanned:false` before a scan.
The updated Client allows120 seconds plus0.5 seconds transport margin for discovery. No-response
does **not** prove a panel is absent: old firmware, invalid cached NVM ID, or
communication problems also prevent discovery. Address 0 is probed as requested,
but the current NVM reader only validates IDs 1..511.

## Expected inventory and discovery notifications

The server stores `/var/lib/rs485-server/discovery-history.json`, containing
the expected inventory and pending discovery notifications. For compatibility,
`last_discovered` is the persisted expected address list: the union of addresses
seen in completed, verified-powered scans. No discovery removes an expected
address, including manual and partial-range scans. Newly found addresses are
added automatically. The HTTP `/panels` result includes `discovery_history`;
its ordinary `addresses` and `panels` still describe the current completed scan.

Service startup and successful all-channel power-on discovery compare the
current result against expected addresses within the scanned range and queue
Pushover warnings for missing panels. Each later power-on can warn again if
those panels are still absent, even after the prior warning was delivered.
Manual discovery updates the current result and adds newly seen addresses but
does not queue warnings or forget missing panels.

V6 is checked before and after the scan. Both checks must indicate ON (any of
the six readings >=2V) before updating the baseline or generating a warning.
OFF/unknown scans preserve the previous list and suppress warnings. Aborted
scans do not update history. This avoids treating powered-off panels as newly
missing. A new scan after power restoration is still required to discover them.

Startup and power-on missing-panel warnings are **notification only**, independent of the
temperature monitor's two-panel coverage protection. This component has no
power-off operation. It uses the configured Pushover recipients from the
optional systemd EnvironmentFile `/etc/roc-temperature-monitor/pushover.env`.
Credentials are read by systemd before dropping privileges to mu2e. Pending
messages and recipient hashes survive restart; failures retry independently
every 30 seconds. Delivery requires a fresh ON power reading; queued warnings
wait while power is OFF or unknown. Credentials are never stored in history or
included in log errors.
As with any network notification, a crash after delivery but before saving its
receipt can cause a duplicate on retry.

Deploy `discovery_history.py`, the updated server and systemd unit together.
The unit creates its writable StateDirectory and loads notification settings.
Existing version-1 history and pending messages load without migration. This
fix preserves the saved baseline going forward; it cannot reconstruct addresses
already erased by older software. Restore such addresses only from verified
historical discoveries or an operator-confirmed roster. To retire or replace an
expected address intentionally, edit `last_discovered` in the history file while
`rs485-server` is stopped (back up the file and preserve its other fields).
There is no automatic pruning or live HTTP operation to remove expectations.
`--discovery-history` changes the history path; `--commands` selects the existing
LVHV opcode header for read-only V6 checks.

## Rediscovery after all-channel LV power-on

The LVHV server sends a nonblocking local datagram after its all-channel
`powerOn` operation returns success: channel6 staggers outputs by50ms, while
channel7 retains the prior sequence without deliberate spacing. Both send one
event only after completion. Bare `Client.py` `powerOn` and `powerOn all` now use
channel6. Individual `powerOn 0` through
`powerOn 5`, power-off, and failed all-channel power-on do not send this event.
The event is `lv-all-on-v1` at `/run/rs485-server/power-on.sock`; systemd creates
the runtime directory and the RS485 service owns a mode-0600 socket. Root LVHV
can send to it. An unavailable receiver or full queue is logged by LVHV and
does not change the power command's result. Events are best-effort, not durable.

RS485 waits `--power-on-delay` seconds (default 5, configurable boot allowance,
not a measured guarantee for every panel) and verifies V6 indicates ON. A
background worker scans addresses 0..300, preserving the normal HTTP interface
and UART ownership. Pending events coalesce and restart the boot delay. Busy
transactions and transient errors are retried within a 60-second window after
the delay; expiry is logged. OFF cancels the request; unknown power waits/retries.
Requests arriving during a scan schedule another pass after it finishes.

The completed result becomes the current discovery used by Graphite and the
temperature monitor on their next polling cycles. Saved history is updated
under the existing power checks, preserving expected addresses and queuing
Pushover warnings for any missing panels. Discovery takes turns
with sensor reads and publishes the new list only after a complete scan.
Neither service restarts in response to the event, and discovery sends no power,
reset, or firmware commands. For manual server launches outside systemd, provide
an existing writable parent directory with `--power-on-socket`.

Deploy the new `power_on_discovery.py`, updated server/unit, and rebuilt LVHV
binary together. **Activating a new LVHV binary requires a maintenance window:**
the existing LVHV startup initializes GPIO/I2C and drives global LV enable low.
Do not restart LVHV on powered detector hardware merely to enable this feature.
Installing the source or compiling in a temporary directory does not activate it.
