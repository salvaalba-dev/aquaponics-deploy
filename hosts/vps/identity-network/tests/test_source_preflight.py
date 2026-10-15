"""Exercise drift refusal and the patch against a captured function fixture."""

import hashlib
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_preflight", ROOT / "proposals/check_notebooklm_source.py"
)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class TestSourcePreflight(unittest.TestCase):
    def setUp(self):
        # This text preserves existing source, including its legacy comment.
        self.before = (ROOT / "tests/fixtures/wake-before.txt").read_bytes()
        self.after = (ROOT / "proposals/notebooklm-wake.candidate.js").read_bytes()
        self.source = b"\n" * 67 + self.before + b"\n// Unchanged tail.\n"

    def test_captured_function_matches_the_live_read_only_fingerprint(self):
        self.assertEqual(
            hashlib.sha256(self.before).hexdigest(), PREFLIGHT.FUNCTION_SHA256
        )

    def test_refuses_source_and_function_drift_and_duplicate_functions(self):
        self.assertFalse(
            PREFLIGHT.assess(self.source, self.before, self.after, "0" * 64)[
                "source_ready"
            ]
        )
        for before, source in (
            (self.before + b" ", self.source),
            (self.before, self.source + self.before),
        ):
            expected = hashlib.sha256(source).hexdigest()
            self.assertFalse(
                PREFLIGHT.assess(source, before, self.after, expected)["source_ready"]
            )

    def test_preflight_only_computes_a_candidate_without_mutating_source(self):
        expected = hashlib.sha256(self.source).hexdigest()
        result = PREFLIGHT.assess(self.source, self.before, self.after, expected)
        self.assertTrue(result["source_ready"])
        self.assertEqual(
            result["candidate_sha256"],
            hashlib.sha256(
                b"\n" * 67 + self.after + b"\n// Unchanged tail.\n"
            ).hexdigest(),
        )
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), expected)

    @unittest.skipUnless(shutil.which("git"), "Git required for patch verification")
    def test_exact_patch_replaces_only_the_captured_function(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notebooklm-web.js"
            path.write_bytes(self.source)
            patch = ROOT / "proposals/notebooklm-service-control.patch"
            for options in (["--check"], []):
                result = subprocess.run(
                    ["git", "-c", "core.autocrlf=false", "apply", *options, str(patch)],
                    cwd=directory,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(
                path.read_bytes(), b"\n" * 67 + self.after + b"\n// Unchanged tail.\n"
            )


if __name__ == "__main__":
    unittest.main()
