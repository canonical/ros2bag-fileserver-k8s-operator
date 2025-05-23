# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness

from auth_devices_keys import AuthDevicesKeysConsumer

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

    def setup_charm_relation(self) -> int:
        """Create relations used by test cases."""
        self.assertEqual(self.harness.charm._stored.auth_devices_keys_events, 0)
        rel_id = self.harness.add_relation("auth-devices-keys", "provider")
        self.harness.add_relation_unit(rel_id, "provider/0")
        self.harness.update_relation_data(
            rel_id,
            "provider",
            {
                "auth-devices-keys": json.dumps(SOURCE_DATA),
            },
        )
        return rel_id

    def test_consumer_auth_devices_keys_available(self):
        rel_id = self.setup_charm_relation()

        rel_data = self.harness.get_relation_data(rel_id, "provider")

        self.assertEqual(
            rel_data["auth-devices-keys"],
            SOURCE_DATA_ASSERTION,
        )
