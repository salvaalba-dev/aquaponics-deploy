#!/usr/bin/env python3
"""Mint a signed download URL for a recording.

Usage:
  python3 mint-url.py <filename> [--expires HOURS] [--base https://meet.aquaponicsunited.com]
                        [--secret /opt/recordings-serve/.secret]

Prints the full URL (and the bare token with --token-only).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serve import load_secret, make_token

DEFAULT_BASE = "https://meet.aquaponicsunited.com"
DEFAULT_SECRET = "/opt/recordings-serve/.secret"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filename")
    ap.add_argument("--expires", type=float, default=24.0, help="validity in hours (default 24)")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--secret", default=DEFAULT_SECRET)
    ap.add_argument("--token-only", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.secret):
        raise SystemExit(f"secret file not found: {args.secret}")

    secret = load_secret(args.secret)
    expires = int(time.time()) + int(args.expires * 3600)
    token = make_token(secret, args.filename, expires)
    if args.token_only:
        print(token)
        return
    from urllib.parse import quote
    print(f"{args.base}/dl/{token}/{quote(args.filename)}")


if __name__ == "__main__":
    main()
