"""Controller tests: fake PID 1 and real local sockets, never a live browser."""

import importlib.util
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROPOSALS = Path(__file__).resolve().parents[1] / "proposals"


def load(name):
    spec = importlib.util.spec_from_file_location(name, PROPOSALS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(sys.platform == "linux", "Linux peer credentials required")
class TestBrowserStartBroker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.broker = load("alma_browser_start_broker")
        cls.client = load("alma_browser_start_client")

    def connection(self, uid=1059, chunks=(b"ENSURE\n", b"")):
        connection = Mock(family=socket.AF_UNIX)
        connection.getsockopt.side_effect = [
            socket.SOCK_STREAM,
            struct.pack("3i", 1234, uid, uid),
        ]
        connection.recv.side_effect = chunks
        return connection

    def test_peer_identity_is_checked_before_request_or_service_access(self):
        for uid in (1000, 1060):
            connection = self.connection(uid=uid)
            start = Mock()
            self.assertFalse(self.broker.handle_connection(connection, 1059, start))
            connection.recv.assert_not_called()
            start.assert_not_called()
        connection = self.connection()
        self.assertFalse(self.broker.handle_connection(connection, 0, Mock()))

    def test_exact_operation_requires_eof_and_accepts_fragmented_frames(self):
        for chunks in (
            (b"ENSURE\n", b""),
            (b"EN", b"SU", b"RE\n", b""),
        ):
            with self.subTest(chunks=chunks):
                start = Mock(return_value=True)
                connection = self.connection(chunks=chunks)
                self.assertTrue(self.broker.handle_connection(connection, 1059, start))
                start.assert_called_once_with()
                connection.sendall.assert_called_once_with(b"STARTED\n")

    def test_rejects_commands_arguments_multiple_requests_and_missing_eof(self):
        for request in (
            b"",
            b"ENSURE",
            b"START\n",
            b"ENSURE\nX",
            b"ENSURE\nENSURE\n",
            b"chrome-paco\n",
            b"ENSURE 18802\n",
            b"ENSURE\x00",
            b"x" * 100,
        ):
            start = Mock()
            # recv always obeys the byte limit, as the real stream does.
            remaining = bytearray(request)
            connection = self.connection()

            def receive(limit, remaining=remaining):
                chunk = bytes(remaining[:limit])
                del remaining[:limit]
                return chunk

            connection.recv.side_effect = receive
            self.assertFalse(self.broker.handle_connection(connection, 1059, start))
            start.assert_not_called()
        connection = self.connection(chunks=(b"ENSURE\n", TimeoutError()))
        start = Mock()
        self.assertFalse(self.broker.handle_connection(connection, 1059, start))
        start.assert_not_called()

    def test_failure_does_not_report_health_or_leak_subprocess_output(self):
        connection = self.connection()
        self.assertFalse(self.broker.handle_connection(connection, 1059, lambda: False))
        connection.sendall.assert_called_once_with(b"ERROR\n")
        with patch.object(self.broker.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(self.broker.start_browser())
            args, kwargs = run.call_args
            self.assertEqual(
                args,
                (
                    (
                        "/usr/bin/systemctl",
                        "--no-ask-password",
                        "start",
                        "chrome-alma.service",
                    ),
                ),
            )
            self.assertNotIn("shell", kwargs)
            self.assertEqual(
                kwargs["env"], {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/"}
            )
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertEqual(kwargs["timeout"], 25)
            self.assertTrue(kwargs["close_fds"])
            run.side_effect = subprocess.TimeoutExpired("fixed", 25)
            self.assertFalse(self.broker.start_browser())

    def test_root_admin_allowed_but_unknown_target_account_denied(self):
        self.assertTrue(
            self.broker.handle_connection(self.connection(uid=0), 1059, lambda: True)
        )
        with (
            patch.object(self.broker.os, "geteuid", return_value=0),
            patch.object(self.broker.sys, "argv", ["broker"]),
            patch.object(self.broker.pwd, "getpwnam", side_effect=KeyError),
        ):
            self.assertEqual(self.broker.main(), 1)

    def test_client_accepts_only_complete_start_response(self):
        for response in (b"ERROR\n", b"STARTED", b"STARTED\nextra", b"", b"DENIED\n"):
            connection = Mock()
            remaining = bytearray(response)

            def receive(limit, remaining=remaining):
                chunk = bytes(remaining[:limit])
                del remaining[:limit]
                return chunk

            connection.recv.side_effect = receive
            self.assertFalse(self.client.request_start(connection))
        connection = Mock()
        connection.recv.side_effect = [b"STAR", b"TED\n", b""]
        self.assertTrue(self.client.request_start(connection))
        connection.sendall.assert_called_once_with(b"ENSURE\n")
        connection.shutdown.assert_called_once_with(socket.SHUT_WR)

    def test_real_unix_peer_and_client_with_no_new_privileges(self):
        uid = os.getuid()
        # Root is allowed for maintenance; the configured account must still be nonroot.
        target_uid = uid if uid else 1059
        results = []
        errors = []
        with tempfile.TemporaryDirectory() as directory:
            address = str(Path(directory) / "start.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(address)
                listener.listen(1)
                listener.settimeout(10)

                def serve():
                    try:
                        with listener.accept()[0] as connection:
                            results.append(
                                self.broker.handle_connection(
                                    connection, target_uid, lambda: True
                                )
                            )
                    except (OSError, ValueError) as error:
                        errors.append(error)

                thread = threading.Thread(target=serve)
                thread.start()
                code = """
import ctypes, importlib.util, socket, sys
libc = ctypes.CDLL(None, use_errno=True)
assert libc.prctl(38, 1, 0, 0, 0) == 0
assert libc.prctl(39, 0, 0, 0, 0) == 1
spec = importlib.util.spec_from_file_location('client', sys.argv[1])
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.connect(sys.argv[2])
    assert client.request_start(connection)
"""
                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-c",
                            code,
                            str(PROPOSALS / "alma_browser_start_client.py"),
                            address,
                        ],
                        capture_output=True,
                        timeout=12,
                        check=False,
                    )
                finally:
                    thread.join(timeout=12)
                self.assertFalse(thread.is_alive())
                self.assertFalse(errors)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(results, [True])

    def test_protocol_deadlines_cannot_be_extended_by_fragmented_input(self):
        connection = self.connection(chunks=(b"EN",))
        start = Mock()
        with patch.object(self.broker.time, "monotonic", side_effect=[0, 1, 3]):
            self.assertFalse(self.broker.handle_connection(connection, 1059, start))
        start.assert_not_called()
        connection = Mock()
        connection.recv.return_value = b"STAR"
        with patch.object(self.client.time, "monotonic", side_effect=[0, 1, 31]):
            self.assertFalse(self.client.request_start(connection))

    def test_non_unix_connection_and_extra_cli_arguments_are_denied(self):
        connection = Mock(family=socket.AF_INET)
        start = Mock()
        self.assertFalse(self.broker.handle_connection(connection, 1059, start))
        start.assert_not_called()
        with patch.object(sys, "argv", ["broker", "chrome-paco"]):
            self.assertEqual(self.broker.main(), 2)
            self.assertEqual(self.client.main(), 2)


if __name__ == "__main__":
    unittest.main()
