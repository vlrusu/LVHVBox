# Bundled LVHV messaging

The API originated from Ed Callaghan's `libmu2e-tracker-messaging` at commit
`2ae238ec79e68de1a85fbdfde57cda4e98fca8ba`, imported October 27, 2026.
The original import is preserved in LVHVBox commit `d0552d4`.

This local implementation fixes the inherited magic-header heap overflow,
unsafe string wrapping, unchecked allocation/element counts, invalid-message
cleanup and partial socket I/O. It rejects unknown types, oversized/truncated
frames and incorrect request shapes, uses full reads/writes with frame deadlines,
and suppresses socket SIGPIPE. The handler validates requests before dispatch
and closes failed transactions without replay. This is protocol hardening;
hardware command semantics remain in their existing handlers.

CMake statically links this source into `lvhv-server`; no site-specific messaging
package, installed header or shared messaging library is required. Wire constants
and request layouts come from the shared [protocol definition](../../protocol/README.md).
That document describes compatibility, limits, generation and tests.
