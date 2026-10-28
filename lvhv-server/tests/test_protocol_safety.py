"""Sanitizers, injected short I/O/OOM, malformed frames and wire compatibility."""
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'common'))
import lvhv_protocol as protocol


class ProtocolSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if not compiler:
            raise RuntimeError('Protocol safety tests require a C compiler')
        cls.directory = tempfile.TemporaryDirectory(prefix='lvhv-protocol-safety-')
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        cls.probe = root / 'probe'
        flags = ['-std=gnu11', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                 '-DLVHV_FRAME_TIMEOUT_MS=150', '-I', str(ROOT / 'lvhv-server/messaging')]
        obj = root / 'messages.o'
        injected = ['-Dmalloc=probe_malloc', '-Dcalloc=probe_calloc', '-Drealloc=probe_realloc',
                    '-Dread=probe_read', '-Dsend=probe_send']
        for command in ([compiler, *flags, *injected, '-c', str(ROOT / 'lvhv-server/messaging/Messages.c'), '-o', str(obj)],
                        [compiler, *flags, str(ROOT / 'lvhv-server/tests/protocol_probe.c'), str(obj), '-o', str(cls.probe)]):
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)

    def environment(self, **changes):
        env = dict(os.environ, UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
                   ASAN_OPTIONS='detect_leaks=' + ('0' if sys.platform == 'darwin' else '1') + ':abort_on_error=1')
        env.update({key: str(value) for key, value in changes.items()})
        return env

    def spawn(self, mode, **environment):
        parent, child = socket.socketpair()
        parent.settimeout(3)
        process = subprocess.Popen([str(self.probe), mode, str(child.fileno())],
            pass_fds=(child.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self.environment(**environment), text=True)
        child.close()

        def cleanup():
            parent.close()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=3)
        self.addCleanup(cleanup)
        return parent, process

    def finish(self, process):
        stdout, stderr = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertNotIn('Sanitizer', stderr)
        self.assertNotIn('runtime error:', stderr)
        return stdout

    def parse(self, payload, **environment):
        parent, process = self.spawn('parse', **environment)
        try:
            parent.sendall(payload)
        except BrokenPipeError:
            pass
        parent.shutdown(socket.SHUT_WR)
        return tuple(map(int, self.finish(process).split()))

    def test_constructor_overflow_string_format_and_cleanup_regressions(self):
        result = subprocess.run([str(self.probe), 'constructors'], env=self.environment(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_constructor_allocation_failures_are_clean(self):
        for allocation in range(1, 30):
            with self.subTest(allocation=allocation):
                result = subprocess.run([str(self.probe), 'constructors'],
                    env=self.environment(FAIL_ALLOCATION=allocation), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_receive_allocation_failures_are_clean(self):
        frame = protocol.encode_request(1, 2, 3, 1.25)
        for allocation in range(1, 18):
            with self.subTest(allocation=allocation):
                received, error, valid = self.parse(frame, FAIL_ALLOCATION=allocation)
                self.assertTrue(received < 0 or valid == 1)

    def test_invalid_and_oversized_headers_fail_before_payload_allocation(self):
        frames = [struct.pack('<I', n) for n in (0, 1025, 0xffffffff)]
        frames += [struct.pack('<I', 1) + kind + struct.pack('<I', count) + payload
                   for kind, count, payload in ((b'Z', 1, b'x'), (b'C', 0, b''),
                       (b'C', 3, b'LVH'), (b'C', 4, b'NOPE'), (b'F', 1, b'LVHV'),
                       (b'D', 0xffffffff, b''))]
        magic = b'\x02\0\0\0C\x04\0\0\0LVHV'
        frames.append(magic + b'D' + struct.pack('<I', (protocol.MAX_MESSAGE_BYTES - 5) // 8))
        for frame in frames:
            with self.subTest(frame=frame):
                self.assertLess(self.parse(frame)[0], 0)

    def test_every_truncated_request_is_rejected_and_freed(self):
        frame = protocol.encode_request(1, 2, 3, 1.25)
        self.assertEqual(self.parse(b'')[0], 0)
        for size in range(1, len(frame)):
            with self.subTest(size=size):
                self.assertLess(self.parse(frame[:size])[0], 0)

    def test_request_shape_is_checked_independently_of_frame_validity(self):
        magic = [('C', tuple(bytes((b,)) for b in protocol.MAGIC))]
        for payload in ([('I', (1,)), ('U', (2,)), ('C', (b'\3',)), ('F', (0.,))],
                        [('U', (1, 2)), ('U', (2,)), ('C', (b'\3',)), ('F', (0.,))], []):
            received, error, valid = self.parse(protocol.encode_message(magic + payload))
            self.assertGreater(received, 0)
            self.assertEqual(valid, 0)

    def test_fragmented_headers_payloads_short_writes_and_interrupted_syscalls(self):
        frame = protocol.encode_request(0xffffffff, 2, 255, 1.25)
        parent, process = self.spawn('echo', FRAGMENT_IO=1)
        for byte in frame:
            parent.sendall(bytes((byte,)))
            time.sleep(.0005)
        reply = protocol.recv_reply(parent, timeout=2)
        self.assertEqual(reply, [('U', (0xffffffff,)), ('U', (2,)), ('C', (b'\xff',)), ('F', (1.25,))])
        self.finish(process)

    def test_large_block_and_all_scalar_types_are_not_clamped(self):
        values = tuple(float(i) for i in range(2048))
        blocks = [('C', tuple(bytes((b,)) for b in protocol.MAGIC)),
                  ('I', (-2147483648, 2147483647)), ('U', (0, 0xffffffff)),
                  ('F', values), ('D', (1.25, -1e100)), ('C', (b'%', b'\0'))]
        parent, process = self.spawn('echo')
        parent.sendall(protocol.encode_message(blocks))
        self.assertEqual(protocol.recv_message(parent, timeout=2), blocks)
        self.finish(process)

    def test_two_messages_on_one_connection_stay_separate(self):
        parent, process = self.spawn('twice', FRAGMENT_IO=1)
        first = protocol.encode_request(1, 2, 3, 0.)
        second = protocol.encode_request(4, 5, 6, 7.)
        parent.sendall(first + second)
        self.assertEqual(protocol.recv_reply(parent, timeout=2)[0], ('U', (1,)))
        self.assertEqual(protocol.recv_reply(parent, timeout=2)[0], ('U', (4,)))
        self.finish(process)

    def test_maximum_block_count_and_reallocation_boundary(self):
        blocks = [('C', tuple(bytes((b,)) for b in protocol.MAGIC))]
        blocks += [('C', ())] * (protocol.MAX_BLOCKS - 1)
        parent, process = self.spawn('echo', FRAGMENT_IO=1)
        parent.sendall(protocol.encode_message(blocks))
        self.assertEqual(protocol.recv_message(parent, timeout=2), blocks)
        self.finish(process)

    def test_mutated_frames_do_not_crash_parser(self):
        rng = random.Random(12000)
        original = protocol.encode_request(1, 2, 3, 1.25)
        for _ in range(32):
            frame = bytearray(original)
            for _ in range(rng.randrange(1, 5)):
                frame[rng.randrange(len(frame))] = rng.randrange(256)
            self.parse(frame)

    def test_partial_frame_times_out_but_idle_persistent_connection_is_preserved(self):
        parent, process = self.spawn('parse')
        time.sleep(.2)
        self.assertIsNone(process.poll())
        parent.sendall(b'\x05')
        received, error, valid = map(int, self.finish(process).split())
        self.assertLess(received, 0)
        self.assertEqual(error, errno.ETIMEDOUT)

    def test_send_to_closed_peer_has_no_sigpipe_or_retry(self):
        parent, process = self.spawn('send')
        parent.close()
        sent, error = map(int, self.finish(process).split())
        self.assertLess(sent, 0)

    def test_send_backpressure_obeys_one_deadline(self):
        parent, process = self.spawn('backpressure')
        sent, error = map(int, self.finish(process).split())
        self.assertLess(sent, 0)
        self.assertEqual(error, errno.ETIMEDOUT)


class DefinitionTests(unittest.TestCase):
    def test_generated_files_are_current(self):
        subprocess.run([sys.executable, str(ROOT / 'protocol/generate.py'), '--check'], check=True)

    def test_generator_detects_changed_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'protocol').mkdir()
            schema = json.loads((ROOT / 'protocol/lvhv.json').read_text())
            (root / 'protocol/lvhv.json').write_text(json.dumps(schema))
            script = ROOT / 'protocol/generate.py'
            subprocess.run([sys.executable, str(script), '--root', str(root)], check=True)
            schema['frame_timeout_ms'] += 1
            (root / 'protocol/lvhv.json').write_text(json.dumps(schema))
            result = subprocess.run([sys.executable, str(script), '--root', str(root), '--check'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_exact_legacy_request_bytes(self):
        # Literal legacy frame: five blocks, LVHV, uint1, uint2, channel3, float1.25.
        expected = bytes.fromhex('0500000043040000004c564856550100000001000000'
                                 '55010000000200000043010000000346010000000000a03f')
        self.assertEqual(protocol.encode_request(1, 2, 3, 1.25), expected)


if __name__ == '__main__':
    unittest.main()
