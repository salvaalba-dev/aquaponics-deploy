"""Check the approved authority against sanitized identity registries only."""

import unittest
from pathlib import Path

import yaml
from phantomorg.spec.service_policy import (
    ServiceApprover,
    ServiceConsumer,
    ServicePolicy,
)

ROOT = Path(__file__).parents[4]


class TestAuthorityFragment(unittest.TestCase):
    def test_confirmed_actor_human_authority_and_private_owner(self):
        org = yaml.safe_load(
            (ROOT / "phantomdocs/au-org.sanitized.yaml").read_text(encoding="utf-8")
        )
        fragment = yaml.safe_load(
            (
                ROOT
                / "hosts/vps/identity-network/proposals/alma-service-policy.fragment.yaml"
            ).read_text()
        )
        policy = ServicePolicy.from_dict(fragment["service_policy"])
        self.assertEqual(policy.version, 2)
        self.assertEqual(
            policy.reference_errors(
                {a["id"] for a in org["actors"]}, {h["id"] for h in org["humans"]}
            ),
            [],
        )
        self.assertEqual(len(policy.services), 1)
        service = policy.services[0]
        self.assertEqual(service.owner_actor, "alma")
        self.assertEqual(service.consumers, (ServiceConsumer("actor", "alma"),))
        self.assertEqual(service.approval, "per-request")
        self.assertEqual(
            set(service.approval_principals()),
            {ServiceApprover("actor", "paco"), ServiceApprover("human", "salvador")},
        )
