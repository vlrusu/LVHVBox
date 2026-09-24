#!/usr/bin/env python3
"""Direct RS485 telemetry CLI. Stop rs485-server before using the UART here."""
import argparse
import signal
import sys

from rs485 import RS485, ROCError, Packet, CONTROL_REQUEST, GOLDEN_GUARD


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address', type=int, help='ROC/MN address, 0..511')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--recover-golden', action='store_true', help='Reprogram/restart this ROC from SPI image 0; interrupts DAQ')
    actions.add_argument('--panel-id', action='store_true', help='Read cached panel ID without CPU')
    actions.add_argument('--recovery-status', action='store_true', help='Read FPGA recovery status without CPU')
    actions.add_argument('--name', help='Parameter name; omit to read all')
    actions.add_argument('--direct', nargs='?', const='all', metavar='NAME',
                         help='Read FPGA TVS without CPU; omit NAME to read all four')
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
        if args.panel_id:
            if not 0 <= args.address <= 511:
                raise ValueError('panel address must be 0..511')
            if args.dry_run:
                print('PANEL ID: ' + Packet(CONTROL_REQUEST, args.address, 0, 2).encode().hex(' '))
                return 0
            with device:
                print(device.panel_id(args.address))
            return 0
        if args.recover_golden or args.recovery_status:
            if not 1 <= args.address <= 511:
                raise ValueError('recovery address must be 1..511')
            if args.dry_run:
                packet = Packet(CONTROL_REQUEST, args.address, 0, 1 if args.recover_golden else 0,
                                GOLDEN_GUARD if args.recover_golden else b'')
                print(('ACTIVATE GOLDEN IMAGE 0 / RESTART ROC' if args.recover_golden else 'RECOVERY STATUS') +
                      f' MN{args.address:03d}: ' + packet.encode().hex(' '))
                return 0
            with device:
                print(device.recovery(args.address, activate=args.recover_golden))
            return 0
        if args.direct is not None:
            targets = ([name for name, rule in device.rules.items() if 'direct_command' in rule]
                       if args.direct == 'all' else [args.direct])
        else:
            targets = [args.name] if args.name else list(device.rules)
        for name in targets:
            device.validate(args.address, name, args.panel, require_calibration=not args.dry_run)
            if args.direct is not None:
                device.direct_command(name)
        if args.dry_run:
            for request in device.preview(args.address, targets, direct=args.direct is not None):
                print(f"{request['name']:<20} cmd={request['command']} request={request['request']}")
            return 0
        failed = False
        with device:
            for name in targets:
                try:
                    print(device.read(args.address, name, args.panel, direct=args.direct is not None)['formatted'])
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
