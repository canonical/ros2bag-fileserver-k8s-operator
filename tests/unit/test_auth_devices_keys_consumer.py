# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest

from charms.auth_devices_keys_k8s.v0.auth_devices_keys import AuthDevicesKeysConsumer

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness

if "unittest.util" in __import__("sys").modules:
    # Show full diff in self.assertEqual.
    __import__("sys").modules["unittest.util"]._MAX_LENGTH = 999999999

MODEL_INFO = {"name": "testing", "uuid": "abcdefgh-1234"}

SOURCE_DATA = [
    {
        "uid": "rob-cos-demo-robot-1",
        "public_ssh_key": "ssh-rsa AAAAB3NzaC1yc2EAAA",
    },
    {
        "uid": "rob-cos-demo-robot-2",
        "public_ssh_key": "ssh-rsa public-key-ash",
    },
]

SOURCE_DATA_ASSERTION = '[{"uid": "rob-cos-demo-robot-1", "public_ssh_key": "ssh-rsa AAAAB3NzaC1yc2EAAA"}, {"uid": "rob-cos-demo-robot-2", "public_ssh_key": "ssh-rsa public-key-ash"}]'
# SOURCE_DATA = {
#     "00001": "ssh-rsa public-key-ash",
#     "00002": "ssh-rsa AAAAB3NzaC1yc2EAAAmVDT4Njl",
# }

# SOURCE_DATA_ASSERTION = (
#     '{"00001": "ssh-rsa public-key-ash", "00002": "ssh-rsa AAAAB3NzaC1yc2EAAAmVDT4Njl"}'
# )


class ConsumerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._stored.set_default(auth_devices_keys_events=0)

        self.auth_devices_keys_consumer = AuthDevicesKeysConsumer(self)
        self.framework.observe(
            self.auth_devices_keys_consumer.on.auth_devices_keys_changed,
            self.auth_devices_keys_events,
        )

    def auth_devices_keys_events(self, _):
        self._stored.auth_devices_keys_events += 1


class TestAuthDevicesKeysConsumer(unittest.TestCase):
    def setUp(self):
        meta = open("metadata.yaml")
        self.harness = Harness(ConsumerCharm, meta=meta)
        self.harness.set_model_info(name=MODEL_INFO["name"], uuid=MODEL_INFO["uuid"])
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def setup_charm_relations(self) -> list:
        """Create relations used by test cases."""
        rel_ids = []
        self.assertEqual(self.harness.charm._stored.auth_devices_keys_events, 0)
        rel_id = self.harness.add_relation("auth_devices_keys", "provider")
        self.harness.add_relation_unit(rel_id, "provider/0")
        rel_ids.append(rel_id)
        self.harness.update_relation_data(
            rel_id,
            "provider",
            {
                "auth_devices_keys": json.dumps(SOURCE_DATA),
            },
        )

        return rel_ids

    def test_consumer_auth_devices_keys_available(self):
        self.assertEqual(self.harness.charm._stored.auth_devices_keys_events, 0)
        self.setup_charm_relations()
        self.assertEqual(self.harness.charm._stored.auth_devices_keys_events, 1)

        self.assertEqual(
            self.harness.charm.auth_devices_keys_consumer.relation_data["auth_devices_keys"],
            SOURCE_DATA_ASSERTION,
        )
