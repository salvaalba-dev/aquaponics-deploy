"""Check AU's candidate binding against pinned generic code, not a live account."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]


@unittest.skipUnless(sys.platform == "linux", "The standalone controller targets Linux")
class TestControllerBinding(unittest.TestCase):
    def test_alma_binding_uses_generic_controller_without_private_code_copy(self):
        source = ROOT / "_product/persona-service-control/persona_service_control.py"
        spec = importlib.util.spec_from_file_location("persona_service_control", source)
        control = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = control
        spec.loader.exec_module(control)
        data = json.loads(
            (
                ROOT / "hosts/vps/identity-network/proposals/alma-browser.binding.json"
            ).read_text()
        )
        self.assertEqual(
            data,
            {
                "version": 1,
                "id": "alma-browser",
                "account": "pb-alma",
                "uid": 1059,
                "unit": "chrome-alma.service",
            },
        )

        def lookup(account):
            self.assertEqual(account, "pb-alma")
            # Synthetic GID only: the actual primary group must be resolved on the
            # approved target during deployment validation. This is not VPS evidence.
            return SimpleNamespace(pw_uid=1059, pw_gid=23456)

        binding = control.parse_binding(data, lookup)
        self.assertEqual(
            binding.socket_path, "/run/persona-service-control/alma-browser.sock"
        )
        units = control.render_units(binding)
        handler = units["persona-service-start-alma-browser@.service"]
        self.assertIn("/usr/local/libexec/persona_service_control.py broker", handler)
        self.assertIn("NoNewPrivileges=yes", handler)
        proposals = ROOT / "hosts/vps/identity-network/proposals"
        self.assertEqual(list(proposals.glob("*.py")), [])
        self.assertEqual(list(proposals.glob("*.sh")), [])


if __name__ == "__main__":
    unittest.main()
