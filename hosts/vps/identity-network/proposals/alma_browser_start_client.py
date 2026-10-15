"""Fixed browser-start request usable without setuid or sudo elevation."""

import os
import socket
import stat
import sys
import time

SOCKET_PATH = "/run/phantomorg/alma-browser-start.sock"


def request_start(connection):
    """STARTED means only that systemctl start succeeded, not browser health."""
    connection.settimeout(30)
    deadline = time.monotonic() + 30
    connection.sendall(b"ENSURE\n")
    connection.shutdown(socket.SHUT_WR)
    response = bytearray()
    while len(response) <= 8:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        connection.settimeout(remaining)
        chunk = connection.recv(9 - len(response))
        if not chunk:
            break
        response.extend(chunk)
    return bytes(response) == b"STARTED\n"


def main():
    if len(sys.argv) != 1:
        return 2
    try:
        parent = os.lstat(os.path.dirname(SOCKET_PATH))
        endpoint = os.lstat(SOCKET_PATH)
        if not (
            stat.S_ISDIR(parent.st_mode)
            and parent.st_uid == 0
            and not parent.st_mode & 0o022
            and stat.S_ISSOCK(endpoint.st_mode)
            and endpoint.st_uid == 0
            and stat.S_IMODE(endpoint.st_mode) == 0o660
        ):
            return 1
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(SOCKET_PATH)
            return 0 if request_start(connection) else 1
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
