"""Handle one systemd-accepted AF_UNIX connection; never authorize a query."""

import os
import pwd
import socket
import struct
import subprocess
import sys
import time

REQUEST = b"ENSURE\n"
START_COMMAND = (
    "/usr/bin/systemctl",
    "--no-ask-password",
    "start",
    "chrome-alma.service",
)


def start_browser():
    """Ask PID 1 to start the fixed unit without inheriting caller input."""
    try:
        result = subprocess.run(
            START_COMMAND,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/"},
            cwd="/",
            timeout=25,
            check=False,
            close_fds=True,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def handle_connection(connection, allowed_uid, start):
    """Authenticate kernel peer credentials before reading the bounded request."""
    try:
        if connection.family != socket.AF_UNIX:
            return False
        if (
            connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            != socket.SOCK_STREAM
        ):
            return False
        peer = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _, uid, _ = struct.unpack("3i", peer)
        if uid not in (0, allowed_uid) or allowed_uid <= 0:
            return False
        deadline = time.monotonic() + 2
        request = bytearray()
        while len(request) <= len(REQUEST):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            connection.settimeout(remaining)
            chunk = connection.recv(len(REQUEST) + 1 - len(request))
            if not chunk:
                break
            request.extend(chunk)
        if bytes(request) != REQUEST:
            connection.sendall(b"DENIED\n")
            return False
        # A complete request must be followed by EOF, not a second operation.
        # The extra-byte read above also rejects a trailing payload.
        started = start()
        connection.sendall(b"STARTED\n" if started else b"ERROR\n")
        return started
    except (OSError, ValueError, struct.error):
        return False


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 2
    try:
        allowed_uid = pwd.getpwnam("pb-alma").pw_uid
        with socket.socket(fileno=os.dup(0)) as connection:
            return 0 if handle_connection(connection, allowed_uid, start_browser) else 1
    except (KeyError, OSError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
