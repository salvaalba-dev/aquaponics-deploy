#!/usr/bin/env python3
"""Resolve explicit meeting delivery context; never infer it from the title."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class RoutePending(ValueError):
    """Delivery must wait for an explicit, valid destination."""


def department(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise RoutePending("invalid-department")
    return value


def read_small(path):
    with path.open("rb") as source:
        value = source.read(65537)
    if len(value) > 65536:
        raise RoutePending("routing-metadata-too-large")
    return value.decode("utf-8")


def resolve(recording, lookup_python, lookup_script, run=subprocess.run):
    """Local override, then explicit metadata, then the existing order lookup.

    These inputs are operator-controlled routing metadata, not document text.
    The caller must still require an exact destination in its existing map.
    No input to this helper assigns a document category or reader permission.
    """
    recording = Path(recording)
    override = Path(str(recording) + ".dept")
    metadata = Path(str(recording) + ".meta.json")
    if override.exists():
        return department(read_small(override).strip())
    if metadata.exists():

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise RoutePending("duplicate-routing-field")
                result[key] = value
            return result

        document = json.loads(read_small(metadata), object_pairs_hook=unique)
        if not isinstance(document, dict):
            raise RoutePending("invalid-routing-metadata")
        # A present but incomplete metadata file must not fall back to another
        # source that may describe a different meeting or departmental context.
        return department(document.get("department"))
    try:
        result = run(
            [lookup_python, lookup_script, recording.stem],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RoutePending("order-lookup-unavailable") from exc
    if result.returncode:
        # Third-party errors may contain credentials or response bodies.
        raise RoutePending("order-lookup-failed")
    if not result.stdout.strip():
        raise RoutePending("order-context-missing")
    return department(result.stdout.strip())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--lookup-python", required=True)
    parser.add_argument("--lookup-script", required=True)
    args = parser.parse_args(argv)
    try:
        print(resolve(args.recording, args.lookup_python, args.lookup_script))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        reason = (
            str(exc) if isinstance(exc, RoutePending) else "invalid-routing-metadata"
        )
        print("HOLD route: " + reason, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
