"""Fake backend only: never invokes systemctl, curl or nsenter on the test host."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


@unittest.skipUnless(os.name == "posix", "requires a POSIX shell")
class TestEnsure(unittest.TestCase):
    def invoke(
        self,
        args,
        *,
        caller="1059",
        active=True,
        namespace="",
        private="no",
        start_ok=True,
        health_ok=True,
    ):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root / "calls.jsonl"
            backend = root / "backend.py"
            backend.write_text("""#!/usr/bin/env python3
import json,os,sys
with open(os.environ['CALL_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
tool,*args=sys.argv[1:]
if tool=='id': print('1059' if args[-1]=='pb-alma' else '0')
elif tool=='systemctl':
 if args[0]=='show': print(os.environ['NS'] if 'NetworkNamespacePath' in args else os.environ['PRIVATE'])
 elif args[0]=='is-active': sys.exit(0 if os.environ['ACTIVE']=='1' else 1)
 elif args[0]=='start': sys.exit(0 if os.environ['START_OK']=='1' else 1)
elif tool=='nsenter': sys.exit(0 if os.environ['HEALTH_OK']=='1' else 1)
""")
            backend.chmod(0o700)
            source = (ROOT / "proposals/chrome-alma-ensure.sh").read_text()
            # Only executable paths change in the disposable test copy. Production
            # accepts no environment overrides for its privileged executables.
            for tool in ("id", "systemctl", "nsenter", "sleep"):
                source = source.replace("/usr/bin/" + tool, f'"{backend}" {tool}')
            script = root / "helper.sh"
            script.write_text(source)
            env = {
                **os.environ,
                "SUDO_UID": caller,
                "CALL_LOG": str(log),
                "NS": namespace,
                "PRIVATE": private,
                "ACTIVE": str(int(active)),
                "START_OK": str(int(start_ok)),
                "HEALTH_OK": str(int(health_ok)),
            }
            result = subprocess.run(
                ["/bin/bash", str(script), *args],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            calls = (
                [json.loads(s) for s in log.read_text().splitlines()]
                if log.exists()
                else []
            )
            return result, calls

    def test_rejects_service_port_and_extra_arguments_without_backend_access(self):
        for args in (
            [],
            ["ssh"],
            ["chrome-alma", "18802"],
            ["chrome-alma;id"],
            ["--help"],
        ):
            with self.subTest(args=args):
                result, calls = self.invoke(args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(calls, [])

    def test_rejects_different_identity_before_service_access(self):
        result, calls = self.invoke(["chrome-alma"], caller="1054")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(any(c[0] == "systemctl" for c in calls))

    def test_active_service_is_not_restarted_and_host_namespace_is_explicit(self):
        result, calls = self.invoke(["chrome-alma"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[:2] == ["systemctl", "start"] for c in calls))
        probe = next(c for c in calls if c[0] == "nsenter")
        self.assertIn("--net=/proc/1/ns/net", probe)
        self.assertIn("http://127.0.0.1:18802/json/version", probe)

    def test_inactive_service_starts_once_and_probes_named_namespace(self):
        result, calls = self.invoke(
            ["chrome-alma"], active=False, namespace="/run/netns/po-example"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(c[:2] == ["systemctl", "start"] for c in calls), 1)
        self.assertIn(
            "--net=/run/netns/po-example", next(c for c in calls if c[0] == "nsenter")
        )

    def test_unknown_namespace_and_start_failure_do_not_probe(self):
        for options in (
            {"namespace": "/tmp/namespace"},
            {"private": "yes"},
            {"active": False, "start_ok": False},
        ):
            with self.subTest(options=options):
                result, calls = self.invoke(["chrome-alma"], **options)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c[0] == "nsenter" for c in calls))

    def test_probe_failure_is_bounded_and_reported(self):
        result, calls = self.invoke(["chrome-alma"], health_ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sum(c[0] == "nsenter" for c in calls), 80)


if __name__ == "__main__":
    unittest.main()
