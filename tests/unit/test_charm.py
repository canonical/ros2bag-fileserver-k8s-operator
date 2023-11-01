# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import patch

import ops
import ops.testing
from charm import Ros2bagFileserverCharm
import yaml

ops.testing.SIMULATE_CAN_CONNECT = True

CADDYFILE_PATH = "srv/Caddyfile"


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(Ros2bagFileserverCharm)
        self.addCleanup(self.harness.cleanup)

        self.name = "ros2bag-fileserver"
        self.harness.set_model_name("testmodel")
        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready(self.name)

    def test_caddyfile_exists_at_path(self):
        self.harness.container_pebble_ready(self.name)
        self.assertTrue(self.harness.model.unit.get_container(self.name).exists("/srv/Caddyfile"))

    def test_caddyfile_config_is_valid(self):
        self.harness.container_pebble_ready(self.name)

        expected_caddyfile_config = """:80 {
            # Set this path to your site's directory.
            root * /var/lib/caddy-fileserver

            # Enable the static file server.
            file_server browse
            header {
                Access-Control-Allow-Origin *
                Access-Control-Allow-Methods GET, POST, PUT, DELETE, OPTIONS
                Access-Control-Allow-Headers *
            }

            log {
                output file /var/log/access.log
            }
        }"""
        actual_caddyfile_config = (
            self.harness.model.unit.get_container(self.name).pull("/srv/Caddyfile").read()
        )
        self.assertEqual(expected_caddyfile_config, actual_caddyfile_config)

    def test_ros2bag_fileserver_pebble_ready(self):
        # Expected plan after Pebble ready with default config
        command = " ".join(["caddy", "run", "/srv/Caddyfile"])

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

    @patch.multiple("charm.TraefikRouteRequirer", external_host="1.2.3.4")
    @patch("socket.getfqdn", new=lambda *args: "ros2bag-fileserver-0.testmodel.svc.cluster.local")
    def test_ingress_relation_sets_options_and_rel_data(self):
        self.harness.set_leader(True)
        self.harness.container_pebble_ready(self.name)
        rel_id = self.harness.add_relation("ingress", "traefik")
        self.harness.add_relation_unit(rel_id, "traefik/0")

        expected_rel_data = {
            "http": {
                "middlewares": {
                    "juju-sidecar-noprefix-testmodel-ros2bag-fileserver": {
                        "stripPrefix": {
                            "forceSlash": False,
                            "prefixes": ["/testmodel-ros2bag-fileserver"],
                        }
                    },
                    "juju-sidecar-trailing-slash-handler-testmodel-ros2bag-fileserver": {
                        "redirectRegex": {
                            "permanent": False,
                            "regex": "^(.*)\/testmodel-ros2bag-fileserver$",  # noqa
                            "replacement": "/testmodel-ros2bag-fileserver/",
                        }
                    },
                },
                "routers": {
                    "juju-testmodel-ros2bag-fileserver-router": {
                        "entryPoints": ["web"],
                        "middlewares": [
                            "juju-sidecar-trailing-slash-handler-testmodel-ros2bag-fileserver",
                            "juju-sidecar-noprefix-testmodel-ros2bag-fileserver",
                        ],
                        "rule": "PathPrefix(`/testmodel-ros2bag-fileserver`)",
                        "service": "juju-testmodel-ros2bag-fileserver-service",
                    },
                    "juju-testmodel-ros2bag-fileserver-router-tls": {
                        "entryPoints": ["websecure"],
                        "middlewares": [
                            "juju-sidecar-trailing-slash-handler-testmodel-ros2bag-fileserver",
                            "juju-sidecar-noprefix-testmodel-ros2bag-fileserver",
                        ],
                        "rule": "PathPrefix(`/testmodel-ros2bag-fileserver`)",
                        "service": "juju-testmodel-ros2bag-fileserver-service",
                        "tls": {"domains": [{"main": "1.2.3.4", "sans": ["*.1.2.3.4"]}]},
                    },
                },
                "services": {
                    "juju-testmodel-ros2bag-fileserver-service": {
                        "loadBalancer": {
                            "servers": [
                                {
                                    "url": "http://ros2bag-fileserver-0.testmodel.svc.cluster.local:80"
                                }
                            ]
                        }
                    },
                },
            }
        }
        rel_data = self.harness.get_relation_data(rel_id, self.harness.charm.app.name)

        # The insanity of YAML here. It works for the lib, but a single load just strips off
        # the extra quoting and leaves regular YAML. Double parse it for the tests
        self.maxDiff = None
        self.assertEqual(yaml.safe_load(rel_data["config"]), expected_rel_data)

        self.assertEqual(
            self.harness.charm.external_url, "http://1.2.3.4/testmodel-ros2bag-fileserver"
        )
