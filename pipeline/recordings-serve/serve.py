#!/usr/bin/env python3
"""Token-protected file server for meeting recordings.

Serves files from RECORDINGS_DIR at /dl/<token>/<filename>.
Token format: <unix-expiry>.<hex-hmac-sha256(secret, expiry + ':' + filename)>
HMAC secret read from SECRET_FILE (first line, stripped).

Only stdlib — no external dependencies. Bound to 127.0.0.1 by default;
Apache proxies /dl/ from the public HTTPS vhost to this server.

Usage: python3 serve.py [--port 8091] [--dir /var/recordings] [--secret /opt/recordings-serve/.secret]
"""
import argparse
import hashlib
import hmac
import http.server
import os
import posixpath
import time
from urllib.parse import unquote, urlsplit

DEFAULT_SECRET = "/opt/recordings-serve/.secret"
DEFAULT_DIR = "/var/recordings"


def load_secret(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.readline().strip()


def make_token(secret: str, filename: str, expires_unix: int) -> str:
    payload = f"{expires_unix}:{filename}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expires_unix}.{sig}"


def verify_token(secret: str, token: str, filename: str) -> tuple[bool, str]:
    """Return (ok, reason)."""
    try:
        expiry_s, sig = token.split(".", 1)
        expiry = int(expiry_s)
    except (ValueError, AttributeError):
        return False, "malformed token"
    now = int(time.time())
    if expiry < now:
        return False, "token expired"
    payload = f"{expiry}:{filename}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False, "bad signature"
    return True, "ok"


def safe_path(root: str, filename: str) -> str | None:
    """Resolve filename under root, guarding against path traversal."""
    # Reject absolute paths and any '..' after unquoting
    filename = unquote(filename)
    if filename.startswith("/") or ".." in posixpath.normpath(filename).split("/"):
        return None
    full = os.path.realpath(os.path.join(root, filename))
    root_real = os.path.realpath(root)
    if not full.startswith(root_real + os.sep) and full != root_real:
        return None
    return full


class RecordingHandler(http.server.BaseHTTPRequestHandler):
    server_version = "RecordingsServe/1.0"

    def do_GET(self):
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        # Expect: /dl/<token>/<filename>
        if not path.startswith("/dl/"):
            self.send_error(404, "not found")
            return
        rest = path[len("/dl/"):]
        if "/" not in rest:
            self.send_error(400, "bad request")
            return
        token, filename = rest.split("/", 1)
        if not token or not filename:
            self.send_error(400, "bad request")
            return

        secret = load_secret(self.server.secret_file)
        ok, reason = verify_token(secret, token, filename)
        if not ok:
            self.send_error(403, reason)
            return

        full = safe_path(self.server.recordings_dir, filename)
        if full is None or not os.path.isfile(full):
            self.send_error(404, "file not found")
            return

        size = os.path.getsize(full)
        ctype = "video/mp4" if full.endswith(".mp4") else "text/plain; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(full)}"')
        self.send_header("Cache-Control", "private, no-store")
        self.end_headers()
        with open(full, "rb") as f:
            # BaseHTTPRequestHandler has no copyfile helper; stream manually
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
            self.wfile.flush()

    def log_message(self, fmt, *args):
        # keep logs compact; go to stderr/journal
        import sys
        sys.stderr.write(f"[recordings-serve] {self.address_string()} {fmt % args}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--secret", default=DEFAULT_SECRET)
    args = ap.parse_args()

    if not os.path.isfile(args.secret):
        raise SystemExit(f"secret file not found: {args.secret}")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), RecordingHandler)
    server.recordings_dir = os.path.realpath(args.dir)
    server.secret_file = args.secret
    print(f"serving {server.recordings_dir} on 127.0.0.1:{args.port} (secret {args.secret})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
