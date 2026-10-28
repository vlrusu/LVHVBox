# Offline power-on notification tests

The full build uses the existing Linux/ARM LVHV dependencies. Do not execute
`lvhv-server` as a test: its startup initializes hardware and disables LV.

`test_power_on_hook.c` instead links the real power-control functions with fake
GPIO, MCP, timing, logging and message wrappers. All other function sections are
discarded. It checks individual/all-channel powerOn, powerOff, reset failure and
an unavailable notification receiver. Run on Linux with installed build headers:

```sh
build_dir=$(mktemp -d /tmp/lvhv-hook-test.XXXXXX)
cc -ffunction-sections -fdata-sections -I. \
  -DRS485_POWER_ON_SOCKET=\"$build_dir/event.sock\" \
  tests/test_power_on_hook.c i2c_routines.c rs485_notify.c \
  -Wl,--gc-sections -o "$build_dir/test-hook"
"$build_dir/test-hook" "$build_dir/event.sock"
```

From the repository root, the Python suite compiles the real C notifier into a
private library and tests it against a temporary Python socket, including queue
saturation/nonblocking behavior and background discovery scheduling:

```sh
python3 -m unittest discover -s rs485-server/tests -p test_power_on_discovery.py
```

These tests never use the production notification socket or hardware devices.

`test_startup_options.py` compiles the actual server `main()` and `utils.c` with
real application headers and stubbed device, network and thread entry points.
It checks default startup without a configuration file, the remaining `-p`/`-b`/
`-l` options, and rejection of retired `-c`/missing arguments before initialization.
It never starts the production daemon, worker threads or a listening socket.

`test_lv_startup.py` compiles the real control functions with hardware and time
stubs, checking channel6 output/reset/global-enable ordering and five delays,
channel7 without inter-output delays, partial-failure behavior, immediate
shutdown, and a build-time delay override. `test_handler_protocol.py` checks
that only powerOn accepts selector7. `Client/tests/test_cli_lv_startup.py` loads
the real CLI parsing/sending functions with a fake connection and verifies
bare/all/explicit selectors. No test starts the actual server.
