"""Read-only source preflight; never apply a patch or execute the browser tool."""

import argparse
import hashlib
import json
from pathlib import Path

SOURCE = Path("/home/pb-alma/.local/share/phantombot/tools/notebooklm-web.js")
BASE_SHA256 = "03d181079700b7e955ed14ee57a56bacd811366f61b5ffaf91bce0de5ba2cd49"
FUNCTION_SHA256 = "aa4fa2c289cd15fc8aa0bc45d7ac53b18079dc471f23269dd033f051f6bf658f"
ROOT = Path(__file__).resolve().parents[1]


def assess(source, before, after, expected_sha256):
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        return {"source_ready": False, "reason": "source-drift"}
    if (
        hashlib.sha256(before).hexdigest() != FUNCTION_SHA256
        or source.count(before) != 1
    ):
        return {"source_ready": False, "reason": "function-mismatch"}
    candidate = source.replace(before, after, 1)
    return {
        "source_ready": True,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    try:
        result = assess(
            args.source.read_bytes(),
            (ROOT / "tests/fixtures/wake-before.txt").read_bytes(),
            (ROOT / "proposals/notebooklm-wake.candidate.js").read_bytes(),
            BASE_SHA256,
        )
    except OSError:
        result = {"source_ready": False, "reason": "source-unavailable"}
    result.update(deployable=False, enforcement_applied=False)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["source_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
