"""Offline delivery tests: no Drive access, uploads, credentials or services."""

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "route", Path(__file__).with_name("resolve-route.py")
)
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.recording = Path(self.temp.name) / "sample-project-sync.mp4"

    def resolve(self, result=None, **kwargs):
        return route.resolve(
            self.recording, "python", "lookup.py", run=lambda *a, **k: result, **kwargs
        )

    def test_explicit_organization_and_project_routes(self):
        for department in ["secretaria", "almaponia"]:
            with self.subTest(department=department):
                self.assertEqual(
                    self.resolve(SimpleNamespace(returncode=0, stdout=department)),
                    department,
                )

    def test_missing_context_never_defaults_to_secretariat(self):
        with self.assertRaisesRegex(route.RoutePending, "order-context-missing"):
            self.resolve(SimpleNamespace(returncode=0, stdout=""))

    def test_backend_failure_does_not_leak_response(self):
        with self.assertRaisesRegex(route.RoutePending, "^order-lookup-failed$"):
            self.resolve(
                SimpleNamespace(returncode=1, stdout="", stderr="private response")
            )

    def test_timeout_is_pending(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("lookup", 90)

        with self.assertRaisesRegex(route.RoutePending, "order-lookup-unavailable"):
            route.resolve(self.recording, "python", "lookup.py", run=timeout)

    def test_local_override_is_explicit_and_does_not_call_lookup(self):
        Path(str(self.recording) + ".dept").write_text("almaponia\n", encoding="utf-8")
        self.assertEqual(self.resolve(), "almaponia")

    def test_metadata_is_authoritative(self):
        path = Path(str(self.recording) + ".meta.json")
        path.write_text(json.dumps({"department": "almaponia"}), encoding="utf-8")
        self.assertEqual(self.resolve(), "almaponia")
        for content in [
            "{}",
            "[]",
            '{"department":"secretaria","department":"almaponia"}',
            "{bad",
        ]:
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                self.resolve(SimpleNamespace(returncode=0, stdout="secretaria"))

    def test_invalid_values_and_multiple_lines_are_rejected(self):
        for value in [
            "",
            "secretaria\nalmaponia",
            "../secretaria",
            "a@example.invalid",
            "x;command",
        ]:
            with self.subTest(value=value), self.assertRaises(route.RoutePending):
                self.resolve(SimpleNamespace(returncode=0, stdout=value))

    def test_large_metadata_is_rejected(self):
        Path(str(self.recording) + ".dept").write_bytes(b"x" * 65537)
        with self.assertRaisesRegex(route.RoutePending, "routing-metadata-too-large"):
            self.resolve()

    @unittest.skipUnless(
        shutil.which("bash"), "Bash is required for deployment shell tests"
    )
    def test_unknown_department_has_no_inbox_or_email_fallback(self):
        shell = Path(__file__).with_name("post-meeting.sh").read_text(encoding="utf-8")
        functions = shell[shell.index("dept_email(){") : shell.index("audio_report(){")]
        harness = (
            functions
            + """
DEFAULT_DEPT=secretaria
DEPT_MAP='secretaria:secretariat@example.invalid'
DEPT_INBOX_MAP='secretaria:synthetic-inbox|Secretariat'
dept_email unknown
email_status=$?
dept_inbox unknown
inbox_status=$?
test "$email_status" = 1 && test "$inbox_status" = 1
"""
        )
        result = subprocess.run(
            [shutil.which("bash"), "-c", harness],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_shell_validates_route_before_processing(self):
        shell = Path(__file__).with_name("post-meeting.sh").read_text(encoding="utf-8")
        start = shell.index('  if ! dept=$("$WORK_PY" "$ROUTE"')
        end = shell.index('  to=$(dept_email "$dept")', start)
        self.assertIn("continue", shell[start:end])
        self.assertLess(end, shell.index('"$PROC" "$f"'))


if __name__ == "__main__":
    unittest.main()
