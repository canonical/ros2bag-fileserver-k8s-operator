# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import unittest
from unittest.mock import patch

import ops
import ops.testing

from charm import Ros2bagFileserverCharm

ops.testing.SIMULATE_CAN_CONNECT = True

AUTH_DEVICES_KEYS_DATA = [
    {
        "uid": "rob-cos-demo-robot-1",
        "public_ssh_key": "ssh-rsa public-key-ash",
    },
    {
        "uid": "rob-cos-demo-robot-2",
        "public_ssh_key": "ssh-rsa AAAAB3NzaC1yc2EAAAmVDT4Njl",
    },
]


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(Ros2bagFileserverCharm)
        self.addCleanup(self.harness.cleanup)

        patcher = patch.object(Ros2bagFileserverCharm, "_set_ssh_server_port")
        self.mock_set_server_port = patcher.start()
        self.addCleanup(patcher.stop)

        self.name = "ros2bag-fileserver"
        self.harness.set_model_name("testmodel")
        self.harness.set_leader(True)
        self.harness.handle_exec(self.name, [], result=0)
        self.harness.add_network("1.2.3.4")

    def test_ros2bag_fileserver_pebble_ready(self):
        # Expected plan after Pebble ready with default config
        command = " ".join(["caddy", "run", "--config", "/srv/Caddyfile"])

        expected_plan = {
            "services": {
                self.name: {
                    "override": "replace",
                    "summary": "ros2bag-fileserver-k8s service",
                    "command": command,
                    "startup": "enabled",
                }
            },
        }
        self.harness.begin_with_initial_hooks()
        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready(self.name)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan(self.name).to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container(self.name).get_service(self.name)
        self.assertTrue(service.is_running())

        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_ingress_relation_http_rel_data(self):
        rel_id = self.harness.add_relation("ingress-http", "traefik")

        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready(self.name)

        rel_data = self.harness.get_relation_data(rel_id, self.harness.charm.app.name)

        self.assertEqual(rel_data["port"], "80")
        self.assertEqual(rel_data["name"], f'"{self.harness.charm.app.name}"')

    def test_ingress_relation_tcp_rel_data(self):
        rel_tcp_id = self.harness.add_relation("ingress-tcp", "traefik")

        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready(self.name)

        rel_tcp_data = self.harness.get_relation_data(rel_tcp_id, self.harness.charm.unit.name)
        self.assertEqual(rel_tcp_data["port"], "2222")
        self.assertEqual(rel_tcp_data["mode"], "tcp")
        self.assertEqual(rel_tcp_data["name"], f"{self.harness.charm.app.name}/0")

    def test_auth_devices_keys_rel_data(self):
        rel_id = self.harness.add_relation("auth-devices-keys", "cos-registration-server")
        self.harness.add_relation_unit(rel_id, "cos-registration-server/0")

        self.harness.begin_with_initial_hooks()

        self.harness.update_relation_data(
            rel_id,
            "cos-registration-server",
            {
                "auth_devices_keys": json.dumps(AUTH_DEVICES_KEYS_DATA),
            },
        )

        self.assertTrue(
            self.harness.model.unit.get_container(self.name).exists("/root/.ssh/authorized_keys")
        )

        expected_authorized_keys = (
            "ssh-rsa public-key-ash\n" + "ssh-rsa AAAAB3NzaC1yc2EAAAmVDT4Njl\n"
        )

        actual_authorized_keys = (
            self.harness.model.unit.get_container(self.name)
            .pull("/root/.ssh/authorized_keys")
            .read()
        )

        self.assertEqual(expected_authorized_keys, actual_authorized_keys)
