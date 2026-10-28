# Shared LVHV Python transport

`lvhv_protocol.py` is the shared binary codec and bounded socket transport for
LVHV clients and protective services. `lvhv_protocol_generated.py` contains wire
constants and command limits generated from `../protocol/lvhv.json`.

CLI/GUI clients use it through `Client/MessagingConnection.py`; Pi health,
network watchdog, ROC monitor, I2C alerts and RS485 discovery's LVHV voltage reader
use it directly. Hardware-specific shutdown triggers, voltage checks and retry
policy remain in each caller. The ROC RS485 serial codec is a separate protocol.

In a source checkout, callers resolve this sibling `common/` directory. A flat
installation puts both modules on the service interpreter's Python module path
and keeps the imports `import lvhv_protocol` / `import lvhv_protocol_generated`.
There are no compatibility copies in `Client/`. Source deployment manifests and
the standalone ROC/Graphite deployment paths select these files from `common/`.
The legacy Debian package scripts are not the supported source-release workflow.

Regenerate definitions from the checkout root with `python3 protocol/generate.py`;
validate without writing with `python3 protocol/generate.py --check`.
See `../protocol/README.md` for the format, bounds and offline regression tests.
