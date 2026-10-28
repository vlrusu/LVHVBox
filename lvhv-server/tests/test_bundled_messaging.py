"""C/Python protocol compatibility over local socket pairs; no PSU hardware."""
import ctypes
import importlib.util
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bundled_protocol_client", ROOT / "Client/MessagingConnection.py")
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


class BundledProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if compiler is None:
            raise unittest.SkipTest("C compiler required")
        cls.directory = tempfile.TemporaryDirectory(prefix="lvhv-messaging-test-")
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        helper = root / "protocol.c"
        helper.write_text('''#include "Messages.h"
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    int fd = atoi(argv[1]);
    Message_t *message = NULL;
    if (strcmp(argv[2], "error") == 0) message = message_wrap_error(-3);
    else if (message_recv(&message, fd) <= 0 || !message->valid) return 3;
    ssize_t sent = message_send(message, fd);
    message_destroy(message);
    close(fd);
    return sent > 0 ? 0 : 4;
}
''')
        cls.helper = root / "protocol"
        result = subprocess.run([compiler, "-std=gnu11", "-I", str(ROOT / "lvhv-server/messaging"),
            str(ROOT / "lvhv-server/messaging/Messages.c"), str(helper), "-o", str(cls.helper)],
            capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def connection(self, mode="echo"):
        parent, child = socket.socketpair()
        parent.settimeout(3)
        with patch.object(client_module.MessagingConnection, "reestablish"):
            client = client_module.MessagingConnection("local-test-only", 0, timeout=3)
        client.client = parent
        process = subprocess.Popen([str(self.helper), str(child.fileno()), mode],
                                   pass_fds=(child.fileno(),))
        child.close()
        self.addCleanup(client.close)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        self.addCleanup(lambda: process.wait(timeout=3) if process.poll() is not None else None)
        return client, process

    def test_python_request_round_trips_through_bundled_c(self):
        client, process = self.connection()
        client.send_message(ctypes.c_uint(123), ctypes.c_uint(4),
                            ctypes.c_char(b"\x02"), ctypes.c_float(1.25))
        self.assertEqual(client.recv_message(), [(123,), (4,), (b"\x02",), (1.25,)])
        self.assertEqual(process.wait(timeout=3), 0)

    def test_c_error_reply_retains_signed_integer_status(self):
        client, process = self.connection("error")
        self.assertEqual(client.recv_message(), [(-3,)])
        self.assertEqual(process.wait(timeout=3), 0)


if __name__ == "__main__":
    unittest.main()
