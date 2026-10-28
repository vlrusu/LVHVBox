# Shared LVHV protocol

`lvhv.json` is the canonical wire definition for the C server on TCP port 12000
and all Python clients. It defines byte order, magic, types, request field
order/counts and defensive frame limits. Command and subsystem numbers remain
in the existing shared `commands.h`.

After changing the definition, run from the repository root:

```sh
python3 protocol/generate.py
python3 protocol/generate.py --check
```

Commit the definition and both generated files (`common/lvhv_protocol_generated.py`
and `lvhv-server/messaging/Protocol.h`). CMake checks that generated files match
at configuration and on each build. Generation uses only Python's standard library; checked-in
outputs permit running installed clients without a generator or JSON file.

The wire layout remains compatible with existing little-endian ARM/x86 clients:
32-bit unsigned block count, then each block's one-byte type, 32-bit unsigned
element count and packed payload, without padding. The first block is always
`C,4,LVHV`. Requests then contain command `U,1`, subsystem `U,1`, channel `C,1`,
and numeric parameter `F,1`. Integers and IEEE binary32/binary64 values use
explicit little-endian encoding. Replies keep their existing typed payloads.
No protocol version bytes have been added.

`command_limits` defines the shared 12-channel HV range and existing 15,000-count
DAC ceiling. Raw DAC settings must be finite whole counts in `0..15000` and use
channel `0..11` with `TYPE_hv`. C validates command/subsystem pairs, channels and
numeric arguments before queueing and again in the I2C worker; low-level DAC and
cache functions also enforce bounds. Invalid commands return signed error `-3`
without hardware IO. The Python ramp uses the same generated ceiling.

Python framing lives in `common/lvhv_protocol.py`; `MessagingConnection` preserves
its ctypes-based interface while delegating encoding and reading to that module.
The GUI, exporter, network watchdog, ROC monitor, I2C alerts, Pi-health shutdown
client and RS485 discovery's LVHV voltage reader use this codec. The ROC RS485
serial protocol remains separate. Service-specific shutdown triggers and voltage
validation remain in their adapters.
C uses generated constants and request validation with its native socket codec.
Language-specific socket/memory handling remains separate; the wire definition
and golden-byte tests are shared.

Frames are limited to 1024 blocks and 64 MiB including headers. These are
transport bounds, not detector limits. C preserves idle persistent connections;
once the first frame byte arrives, one 10-second deadline covers the remaining
frame. Replies have one 10-second send deadline. Python uses the caller's reply
or transaction timeout. Failed/partial transactions must be discarded; commands
are never automatically reconnected and replayed because they may have executed.
Power-off clients require a valid magic header and the existing signed-integer
zero acknowledgement before reporting success.

For a flat installation, distribute `lvhv_protocol.py` and
`lvhv_protocol_generated.py` alongside `MessagingConnection.py` in the service
interpreter's module path. The source deployment role and standalone ROC monitor
playbook include these modules. The old Debian package scripts are legacy;
use the source deployment workflow for this release.

Offline tests (no daemon or detector handlers are run):

```sh
python3 -m unittest discover -s Client/tests -v
python3 -m unittest discover -s lvhv-server/tests -v
python3 -m unittest discover -s network-watch/tests -v
python3 -m unittest discover -s roc-temperature-monitor/tests -v
python3 -m unittest discover -s rs485-server/tests -v
```

The C protocol probe uses AddressSanitizer/UndefinedBehaviorSanitizer, malformed
and truncated input, injected allocation failures and short/interrupted socket
I/O. Linux also checks leaks. Loopback/socketpair tests may require local socket
permission. A full server build additionally requires the standard Raspberry Pi
build libraries listed by the fleet source deployment role.
