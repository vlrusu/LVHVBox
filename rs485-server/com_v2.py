#!/usr/bin/env python3
"""Direct RS485 telemetry CLI. Stop rs485-server before using the UART here."""
import argparse
import signal
import sys

from rs485 import RS485, ROCError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address', type=int, help='ROC/MN address, 0..511')
    parser.add_argument('--name', help='Parameter name; omit to read all')
    parser.add_argument('--rules', help='Transformation JSON (default: beside this script)')
    parser.add_argument('--calibrations', help='Flow CSV (default: beside this script)')
    parser.add_argument('--panel', help='Flow calibration key; default MN{address:03d}')
    parser.add_argument('--port', default='/dev/ttyAMA0')
    parser.add_argument('--gpiochip', default='/dev/gpiochip0')
    parser.add_argument('--dir-pin', type=int, default=24)
    parser.add_argument('--timeout', type=float, default=6.0)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Preview without opening hardware')
    args = parser.parse_args(argv)
    try:
        device = RS485(args.rules, args.calibrations, port=args.port,
                       gpiochip=args.gpiochip, dir_pin=args.dir_pin,
                       timeout=args.timeout, debug=args.debug)
        targets = [args.name] if args.name else list(device.rules)
        for name in targets:
            device.validate(args.address, name, args.panel, require_calibration=not args.dry_run)
        if args.dry_run:
            for request in device.preview(args.address, targets):
                print(f"{request['name']:<20} cmd={request['command']} request={request['request']}")
            return 0
        failed = False
        with device:
            for name in targets:
                try:
                    print(device.read(args.address, name, args.panel)['formatted'])
                except (ROCError, ValueError, ArithmeticError) as exc:
                    print(f'{name}: {exc}', file=sys.stderr)
                    failed = True
                # UART errors/timeouts abort the scan; never retry automatically.
        return int(failed)
    except KeyboardInterrupt:
        print('Interrupted; RS485 driver released.', file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, KeyError, ImportError, TypeError) as exc:
        print(f'RS485: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    sys.exit(main())
