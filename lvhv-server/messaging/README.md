# Bundled LVHV messaging protocol

`Messages.c` and `Messages.h` originate from Ed Callaghan's
[libmu2e-tracker-messaging](https://github.com/edcallaghan/libmu2e-tracker-messaging)
at commit `2ae238ec79e68de1a85fbdfde57cda4e98fca8ba` (retrieved October 27, 2026).
Original author comments are retained. The imported C code and header are
unchanged; Git blob IDs are respectively
`98333b071971382d2e9a87230c199bd078dca616` and
`311ddf8543b4bd071b1590b2f76b7abce70d3df0`.

CMake builds these files into a static library linked into `lvhv-server`.
Building and running the server requires neither an installed `Messages.h`
nor `libmu2e-tracker-messaging.so`. Existing system installations are untouched.

This is the typed binary protocol used by the server on TCP port 12000.
Python clients use the matching implementation in `Client/MessagingConnection.py`;
the GUI, telemetry collectors and protective shutdown clients retain their
existing request/reply formats. No hardware behavior or protocol change is
intended by bundling the C implementation.
