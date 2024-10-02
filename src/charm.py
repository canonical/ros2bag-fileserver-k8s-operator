#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright 2023 Canonical Ltd.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""A kubernetes charm for storing robotics bag files."""

import logging

from ops.charm import (
    CharmBase,
)

from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus, OpenedPort, ModelError
from ops.pebble import Layer, ConnectionError, ExecError

from charms.catalogue_k8s.v0.catalogue import CatalogueConsumer, CatalogueItem
import socket
from charms.traefik_k8s.v1.ingress_per_unit import (
    IngressPerUnitReadyForUnitEvent,
    IngressPerUnitRequirer,
)

from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
)

from charms.auth_devices_keys_k8s.v0.auth_devices_keys import AuthDevicesKeysConsumer
from charms.blackbox_k8s.v0.blackbox_probes import BlackboxProbesProvider

from urllib.parse import urlparse
import json

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]


class Ros2bagFileserverCharm(CharmBase):
    """Charm to run a ROS 2 bag fileserver on Kubernetes."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = "ros2bag-fileserver"

        self.container = self.unit.get_container(self.name)
        self.caddyfile_config = ""
        self._ssh_port = int(self.config["ssh-port"])
        self.set_ports()

        self.ingress_http = IngressPerAppRequirer(
            self,
            relation_name="ingress-http",
            strip_prefix=True,
            port=80,
        )

        self.ingress_tcp = IngressPerUnitRequirer(
            self,
            relation_name="ingress-tcp",
            port=self._ssh_port,
            mode="tcp",
        )

        self.framework.observe(self.ingress_tcp.on.ready_for_unit, self._on_ingress_ready_tcp)
        self.framework.observe(self.ingress_http.on.ready, self._on_ingress_ready_http)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.ros2bag_fileserver_pebble_ready, self._update_layer_and_restart
        )

        # -- device_keys relation observations
        self.auth_devices_keys_consumer = AuthDevicesKeysConsumer(
            self, relation_name="auth-devices-keys"
        )

        self.framework.observe(
            self.auth_devices_keys_consumer.on.auth_devices_keys_changed,  # pyright: ignore
            self._on_auth_devices_keys_changed,
        )

        self.catalog = CatalogueConsumer(
            charm=self,
            refresh_event=[
                self.on.ros2bag_fileserver_pebble_ready,
                self.ingress_http.on.ready,
                self.on["ingress-http"].relation_broken,
                self.on.config_changed,
            ],
            item=CatalogueItem(
                name="ros2bag fileserver",
                icon="graph-line-variant",
                url=self.external_url + "/",
                description=("ROS 2 bag fileserver to store robotics data."),
            ),
        )

        self.blackbox_probes_provider = BlackboxProbesProvider(
            charm=self,
            probes=self.self_probe,
            refresh_event=[
                self.on.update_status,
                self.ingress_http.on.ready,
                self.on.config_changed,
            ],
        )

    def _on_auth_devices_keys_changed(self, event) -> None:
        container = self.unit.get_container(self.name)

        if not container.can_connect():
            logger.debug("Cannot connect to Pebble yet, deferring event")
            event.defer()
            return

        if not self.auth_devices_keys_consumer.relation_data["auth_devices_keys"]:
            logger.error("No data in the relation")
            return

        auth_devices_keys = self.auth_devices_keys_consumer.relation_data[  # pyright: ignore
            "auth_devices_keys"
        ]

        auth_devices_keys_list = json.loads(auth_devices_keys)

        public_ssh_keys = [entry["public_ssh_key"] + "\n" for entry in auth_devices_keys_list]

        string_of_keys = "".join(public_ssh_keys)
        self.container.push(
            "/root/.ssh/authorized_keys",
            string_of_keys,
            permissions=0o600,
            make_dirs=True,
        )

    def _on_ingress_ready_tcp(self, event: IngressPerUnitReadyForUnitEvent):
        logger.info("Ingress for unit ready on '%s'", event.url)
        self._update_layer_and_restart(event)

    def _on_ingress_ready_http(self, event: IngressPerAppReadyEvent):
        logger.info("Ingress for unit ready on '%s'", event.url)
        if not self.unit.is_leader():
            return
        self._update_layer_and_restart(event)

    def _on_install(self, _):
        """Handler for the "install" event during which we will update the K8s service."""
        self.set_ports()

    def _update_layer_and_restart(self, _) -> None:
        """Define and start a workload using the Pebble API."""
        self.unit.status = MaintenanceStatus("Assembling pod spec")

        self.ingress_tcp.provide_ingress_requirements(
            scheme=urlparse(self.internal_url).scheme, port=self._ssh_port
        )
        self.ingress_http.provide_ingress_requirements(
            scheme=urlparse(self.internal_url).scheme, port=80
        )

        if self.container.can_connect():
            new_layer = self._pebble_layer.to_dict()

            self._set_ssh_server_port("/etc/ssh/sshd_config")

            # Get the current pebble layer config
            services = self.container.get_plan().to_dict().get("services", {})
            if services != new_layer["services"]:  # pyright: ignore
                self.container.add_layer(self.name, self._pebble_layer, combine=True)

                logger.info("Added updated layer 'ros2bag fileserver' to Pebble plan")

                self.container.restart(self.name)
                logger.info(f"Restarted '{self.name}' service")
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for Pebble in workload container")

    def set_ports(self):
        """Open necessary (and close no longer needed) workload ports."""
        planned_ports = (
            {OpenedPort("tcp", int(self.config["ssh-port"]))} if self.unit.is_leader() else set()
        )

        actual_ports = self.unit.opened_ports()

        # Ports may change across an upgrade, so need to sync
        ports_to_close = actual_ports.difference(planned_ports)
        for p in ports_to_close:
            self.unit.close_port(p.protocol, p.port)

        new_ports_to_open = planned_ports.difference(actual_ports)
        for p in new_ports_to_open:
            self.unit.open_port(p.protocol, p.port)

    def _set_ssh_server_port(self, sshd_config_path):
        sshd_config = self.container.pull(sshd_config_path).read()

        if f'Port {self._ssh_port}' in sshd_config:
            return

        try:
            self.container.exec(
                ["sed", "-i", f"s/#Port 22/Port {self._ssh_port}/", sshd_config_path]
            )
            self.container.exec(["service", "ssh", "restart"]).wait()
        except ExecError as e:
            logger.error(f"Error: {e}")

    @property
    def _scheme(self) -> str:
        return "http"

    @property
    def internal_url(self) -> str:
        """Return workload's internal URL. Used for ingress."""
        return f"{self._scheme}://{socket.getfqdn()}:{80}"

    @property
    def external_url(self) -> str:
        """Return the external hostname to be passed to ingress via the relation.

        If we do not have an ingress, then use the pod ip as hostname.
        The reason to prefer this over the pod name (which is the actual
        hostname visible from the pod) or a K8s service, is that those
        are routable virtually exclusively inside the cluster (as they rely)
        on the cluster's DNS service, while the ip address is _sometimes_
        routable from the outside, e.g., when deploying on MicroK8s on Linux.
        """
        try:
            if ingress_url := self.ingress_http.url:
                return ingress_url
        except ModelError as e:
            logger.error("Failed obtaining external url: %s. Shutting down?", e)
        return self.internal_url

    @property
    def self_probe(self):
        """The self-monitoring blackbox probe."""
        probe = {
            'job_name': 'blackbox_http_2xx',
            'params': {
                'module': ['http_2xx']
            },
            'static_configs': [
                {
                    'targets': [self.external_url],
                    'labels': {'name': "ros2bag-fileserver"}
                }
            ]
        }
        return [probe]

    @property
    def _pebble_layer(self):
        """Return a dictionary representing a Pebble layer."""
        command = " ".join(["caddy", "run", "--config", "/srv/Caddyfile"])

        pebble_layer = Layer(
            {
                "summary": "ros2bag fileserver k8s layer",
                "description": "ros2bag fileserver k8s layer",
                "services": {
                    self.name: {
                        "override": "replace",
                        "summary": "ros2bag-fileserver-k8s service",
                        "command": command,
                        "startup": "enabled",
                    }
                },
            }
        )

        return pebble_layer


if __name__ == "__main__":  # pragma: nocover
    main(Ros2bagFileserverCharm)  # type: ignore
