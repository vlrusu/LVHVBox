"""Actual client handler with protocol/task code and hardware-free dispatch stubs."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Client'))
import lvhv_protocol as protocol


class HandlerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='lvhv-handler-boundary-')
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        server = ROOT / 'lvhv-server'
        # Only hardware headers are replaced; the entire real handler is retained.
        source = (server / 'handler.c').read_text().replace('#include "pico_routines.h"', '').replace(
            '#include "pico_registry.h"', '')
        aliases = '\n'.join(line for line in (server / 'pico_routines.h').read_text().splitlines()
                            if line.startswith('#define COMMAND_'))
        (root / 'handler.c').write_text('#include "handler.h"\nint pico_is_connected(size_t);\n' + aliases + '\n' + source)
        cls.probe = root / 'handler'
        result = subprocess.run([shutil.which('cc'), '-std=gnu11', '-g', '-fsanitize=address,undefined',
            '-fno-omit-frame-pointer', '-pthread', '-I', str(server), '-I', str(server / 'messaging'),
            str(root / 'handler.c'), str(server / 'Task.c'), str(server / 'messaging/Messages.c'),
            str(server / 'tests/handler_probe.c'), '-o', str(cls.probe)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def session(self, frame, valid=False):
        parent, child = socket.socketpair()
        parent.settimeout(3)
        with parent, child:
            env = dict(os.environ, UBSAN_OPTIONS='halt_on_error=1', ASAN_OPTIONS='detect_leaks=' +
                       ('0' if sys.platform == 'darwin' else '1') + ':abort_on_error=1')
            process = subprocess.Popen([str(self.probe), str(child.fileno())], pass_fds=(child.fileno(),),
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            child.close()
            try:
                parent.sendall(frame)
                parent.shutdown(socket.SHUT_WR)
                if valid:
                    self.assertEqual(protocol.recv_reply(parent, timeout=2), [('I', (0,))])
                else:
                    self.assertEqual(parent.recv(1), b'')
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertEqual(int(stdout), 1 if valid else 0)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=3)

    def test_malformed_request_never_dispatches(self):
        magic = ('C', tuple(bytes((b,)) for b in protocol.MAGIC))
        for blocks in ([magic], [magic, ('I', (1,)), ('U', (2,)), ('C', (b'\6',)), ('F', (0.,))],
                       [magic, ('U', (1,)), ('U', (2,)), ('C', ()), ('F', (0.,))]):
            with self.subTest(blocks=blocks):
                self.session(protocol.encode_message(blocks))

    def test_valid_request_dispatches_once_and_replies(self):
        codes = {}
        for line in (ROOT / 'commands.h').read_text().splitlines():
            words = line.split('//')[0].split()
            if len(words) >= 3 and words[0] == '#define':
                codes[words[1]] = int(words[2], 0)
        self.session(protocol.encode_request(codes['COMMAND_powerOff'], codes['TYPE_lv'], 6), valid=True)

    def test_unknown_subsystem_disconnects_without_dispatch_or_crash(self):
        self.session(protocol.encode_request(1, 0xffffffff, 6))
