#!/usr/bin/env python3
"""Read archived HV for an OTS run. Never writes to PostgreSQL or hardware."""
import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time


@contextmanager
def database_endpoint(args):
    if args.no_tunnel:
        yield args
        return
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        local_port = reservation.getsockname()[1]
    command = ['ssh', '-N', '-o', 'ExitOnForwardFailure=yes',
               '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
               '-o', 'ServerAliveCountMax=3', '-J', args.jump_host,
               '-L', f'127.0.0.1:{local_port}:{args.host}:{args.port}', args.ssh_host]
    print(f'Opening SSH tunnel through {args.jump_host} to {args.ssh_host}', file=sys.stderr)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise ValueError('SSH tunnel exited before startup; check the SSH error above')
            try:
                with socket.create_connection(('127.0.0.1', local_port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError('SSH tunnel startup timed out')
                time.sleep(0.2)
        local = argparse.Namespace(**vars(args))
        local.host, local.port = '127.0.0.1', local_port
        yield local
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run_window(text):
    """Parse DAQInterface UTC metadata without relying on the laptop timezone."""
    result = []
    for field in ('start', 'stop'):
        matches = re.findall(r'^DAQInterface ' + field + r' time:\s*(.+)$', text, re.M)
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one DAQInterface {field} time; '
                             'use --start/--end for an unfinished or unusual run record')
        stamp = matches[0].strip()
        if ' UTC ' not in stamp:
            raise ValueError('Run metadata must explicitly use UTC; provide --start/--end otherwise')
        # strptime uses the process locale for month/day names; this script sets C.
        result.append(datetime.strptime(stamp, '%a %b %d %I:%M:%S %p UTC %Y')
                      .replace(tzinfo=timezone.utc))
    return validate_window(*result)


def iso_time(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timestamps require an explicit offset, e.g. -05:00 or Z')
    return stamp.astimezone(timezone.utc)


def validate_window(start, end):
    if end <= start:
        raise ValueError('Run end must be later than run start')
    return start, end


def load_metadata(args):
    if args.metadata:
        return Path(args.metadata).read_text(), str(args.metadata)
    # SSH reads a single archived file. Host aliases/ProxyJump use ~/.ssh/config.
    program = '''import pathlib,sys
run=sys.argv[1]
roots=["/home/mu2eshift/ots_trk/Data_trigger/ARTDAQConfigurations/run_records",
       "/home/mu2eshift/ots_ops/Data_trigger/ARTDAQConfigurations/run_records"]
for root in roots:
 p=pathlib.Path(root)/run/"metadata.txt"
 if p.is_file():
  print(p, file=sys.stderr)
  print(p.read_text(), end="")
  break
else:
 print("Run record not found; use --metadata or --start/--end", file=sys.stderr)
 sys.exit(2)
'''
    remote = shlex.join(['python3', '-c', program, str(args.run)])
    proc = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                           args.metadata_host, remote], text=True, capture_output=True,
                          timeout=30)
    if proc.returncode:
        raise ValueError('Cannot read the OTS run record over SSH. Check access to '
                         f'{args.metadata_host}, or use --metadata / --start / --end.')
    return proc.stdout, f'{args.metadata_host}:{proc.stderr.strip()}'


def write_hv_changes(initial, samples, args):
    writer = csv.writer(sys.stdout, delimiter=',' if args.csv or args.samples else '\t')
    writer.writerow(['PSU', 'Channel', 'HV_V', 'Timestamp_UTC'])
    last = {}
    first_times = {}
    missing = []

    def emit(row):
        psu, channel, value, stamp = row
        writer.writerow([psu, channel, '' if value is None else value,
                         '' if stamp is None else stamp.isoformat()])

    for row in initial:
        key = (row[0], row[1])
        last[key], first_times[key] = row[2], row[3]
        emit(row)
        if row[2] is None:
            missing.append(f'psu{key[0]}/ch{key[1]}')
    writer.writerow(['.' * 60])
    if missing:
        print(f'No initial HV value for {len(missing)} channels: ' + ', '.join(missing),
              file=sys.stderr)
    printed = 0
    for row in samples:
        key = (row[0], row[1])
        value, stamp = row[2], row[3]
        if key not in last or value is None:
            continue
        if first_times[key] is not None and stamp <= first_times[key]:
            continue
        if last[key] is None or abs(value - last[key]) > 500:
            emit(row)
            last[key] = value
            printed += 1
            if args.nlines and printed >= args.nlines:
                break


def query(args, start, end):
    try:
        import psycopg2
    except ImportError:
        raise ValueError('Install the driver: python3 -m pip install psycopg2-binary') from None
    settings = dict(host=args.host, port=args.port, dbname=args.database,
                    user=args.user, connect_timeout=10,
                    application_name='mu2e-query-run-hv')
    if args.ask_password:
        settings['password'] = getpass.getpass('PostgreSQL password: ')
    phase = 'connection'
    try:
        connection = psycopg2.connect(**settings)
        phase = 'query'
        try:
            connection.set_session(readonly=True)
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true)",
                                   (str(args.timeout_seconds * 1000),))
                    cursor.execute("SET LOCAL TIME ZONE 'UTC'")
                psu_number = int(args.psu.rsplit('psu', 1)[1]) if args.psu else None
                # Explicit grid includes rows even if metadata or samples are absent.
                with connection.cursor() as cursor:
                    cursor.execute('''
                        SELECT p.psu, ch.channel, first_sample.value, first_sample.time
                        FROM generate_series(0,17) p(psu)
                        CROSS JOIN generate_series(0,11) ch(channel)
                        LEFT JOIN LATERAL (
                            SELECT v.value, v.time
                            FROM public.trk_channel c
                            JOIN public.trk_value v ON v.channel_id = c.id
                            WHERE c.psu = 'mu2e-trk-psu' || p.psu::text
                              AND c.channel = ch.channel AND c.name LIKE %s
                              AND v.time >= %s AND v.time < %s
                            ORDER BY v.time, v.value ASC NULLS LAST LIMIT 1
                        ) first_sample ON true
                        WHERE (%s IS NULL OR p.psu = %s)
                        ORDER BY p.psu, ch.channel
                    ''', ['%.vhv_v', start, end, psu_number, psu_number])
                    initial = cursor.fetchall()
                psus = ([args.psu] if args.psu else
                        [f'mu2e-trk-psu{number}' for number in range(18)])
                sql = '''SELECT substring(c.psu from 'psu([0-9]+)$')::integer,
                                       c.channel, v.value, v.time
                              FROM public.trk_value v
                              JOIN public.trk_channel c ON c.id = v.channel_id
                              WHERE v.time >= %s AND v.time < %s
                                AND c.name LIKE %s AND c.psu = ANY(%s)
                                AND c.channel BETWEEN 0 AND 11
                              ORDER BY v.time,
                                       substring(c.psu from 'psu([0-9]+)$')::integer,
                                       c.psu, c.channel, v.value ASC NULLS LAST'''
                # Named cursor streams large raw-sample exports without loading all rows.
                with connection.cursor(name='run_hv_read') as cursor:
                    cursor.itersize = 2000
                    cursor.execute(sql, [start, end, '%.vhv_v', psus])
                    write_hv_changes(initial, cursor, args)
        finally:
            connection.close()
    except psycopg2.Error as exc:
        # Classify locally; never print raw driver messages, DSNs or passwords.
        message = str(exc).lower()
        causes = [
            (('password authentication failed',), 'Password authentication failed.'),
            (('no password supplied',), 'No password supplied; use --ask-password or a password file.'),
            (('no pg_hba.conf entry',), 'The server does not authorize this client address/user/database. '
             'With a tunnel, use --host mu2e-dcs-01.fnal.gov, not --host 127.0.0.1.'),
            (('could not translate host name', 'name or service not known'), 'Database hostname could not be resolved.'),
            (('connection refused',), 'Database TCP connection refused.'),
            (('timeout expired', 'connection timed out'), 'Database connection timed out; check network/VPN or use an SSH tunnel.'),
            (('statement timeout',), 'Query exceeded --timeout-seconds.'),
            (('permission denied',), 'Database permission denied.'),
            (('certificate verify failed',), 'Database TLS certificate verification failed.'),
        ]
        detail = next((hint for patterns, hint in causes
                       if any(pattern in message for pattern in patterns)),
                      'Check database reachability, credentials and server permissions.')
        raise ValueError(f'PostgreSQL {phase} failed ({type(exc).__name__}). {detail}') from None


def main(argv=None):
    import locale
    locale.setlocale(locale.LC_TIME, 'C')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=int)
    parser.add_argument('--metadata', help='Local OTS run-record metadata.txt; otherwise read via SSH')
    parser.add_argument('--metadata-host', default='calo-01', help='SSH alias (default: calo-01)')
    parser.add_argument('--start', help='Override run start: ISO8601 with timezone')
    parser.add_argument('--end', help='Override run end: ISO8601 with timezone; exclusive')
    parser.add_argument('--psu', help='Optional PSU hostname, e.g. mu2e-trk-psu7')
    parser.add_argument('--samples', action='store_true', help='Compatibility alias for --csv')
    parser.add_argument('--csv', action='store_true', help='CSV instead of tab-separated output')
    parser.add_argument('--nlines', '--limit', dest='nlines', type=int, default=0,
                        help='Maximum change rows after the initial list (default: all changes)')
    parser.add_argument('--no-tunnel', action='store_true', help='Connect directly using --host/--port')
    parser.add_argument('--ssh-host', default='mu2eshift@mu2e-dcs-01.fnal.gov',
                        help='SSH tunnel destination (use the FQDN for Kerberos authentication)')
    parser.add_argument('--jump-host', default='mu2egateway01.fnal.gov', help='SSH gateway')
    parser.add_argument('--dry-run', action='store_true', help='Resolve run times without contacting PostgreSQL')
    parser.add_argument('--host', default=os.getenv('PGHOST', 'mu2e-dcs-01.fnal.gov'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PGPORT', '5434')))
    parser.add_argument('--database', default=os.getenv('PGDATABASE', 'dcs_archive'))
    parser.add_argument('--user', default=os.getenv('PGUSER', 'dcs_writer'))
    parser.add_argument('--ask-password', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=120)
    args = parser.parse_args(argv)
    if args.run <= 0 or args.timeout_seconds <= 0:
        parser.error('run and timeout must be positive')
    if args.nlines < 0:
        parser.error('--nlines must be nonnegative')
    if args.psu and not re.fullmatch(r'mu2e-trk-psu(?:[0-9]|1[0-7])', args.psu):
        parser.error('--psu must be mu2e-trk-psu0 through mu2e-trk-psu17')
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if args.ssh_host.startswith('-') or args.jump_host.startswith('-'):
        parser.error('SSH host names must not start with a dash')
    if bool(args.start) != bool(args.end):
        parser.error('--start and --end must be supplied together')
    if args.metadata and args.start:
        parser.error('Choose --metadata or --start/--end')
    try:
        if args.start:
            start, end = validate_window(iso_time(args.start), iso_time(args.end))
            source = 'explicit user-supplied window (run label not independently verified)'
        else:
            metadata, source = load_metadata(args)
            start, end = run_window(metadata)
        print(f'Run {args.run}: [{start.isoformat()}, {end.isoformat()})\n'
              f'Run window source: {source}', file=sys.stderr)
        if not args.dry_run:
            with database_endpoint(args) as endpoint:
                query(endpoint, start, end)
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
