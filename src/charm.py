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

from charms.devices_pub_keys_manager_k8s.v0.devices_pub_keys import DevicesKeysConsumer
from urllib.parse import urlparse
import ast

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
            port=self.config["ssh-port"],
            mode="tcp",
        )

        self.framework.observe(self.ingress_tcp.on.ready_for_unit, self._on_ingress_ready_tcp)
        self.framework.observe(self.ingress_http.on.ready, self._on_ingress_ready_http)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.ros2bag_fileserver_pebble_ready, self._update_layer_and_restart
        )

        # -- device_keys relation observations
        self.devices_keys_consumer = DevicesKeysConsumer(self)
        self.framework.observe(
            self.devices_keys_consumer.on.devices_keys_changed,  # pyright: ignore
            self._on_devices_keys_changed,
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
                url=self.external_url,
                description=("ROS 2 bag fileserver to store robotics data."),
            ),
        )

    def _on_devices_keys_changed(self, event) -> None:
        self._update_devices_public_keys(event)

    def _update_devices_public_keys(self, event) -> None:
        container = self.unit.get_container(self.name)

        if not container.can_connect():
            logger.debug("Cannot connect to Pebble yet, deferring event")
            event.defer()
            return

        devices_pub_keys_dict = ast.literal_eval(self.devices_keys_consumer._stored.devices_pub_keys)

        pub_keys_list = ""

        for value in devices_pub_keys_dict["ssh_keys"].values():
            pub_keys_list += value + "\n"

        self.container.push(
                        "/root/.ssh/authorized_keys",
                        pub_keys_list,
                        permissions=0o777,
                        make_dirs=True,
                    )

    def _on_ingress_ready_tcp(self, event: IngressPerUnitReadyForUnitEvent):
        logger.info("Ingress for unit ready on '%s'", event.url)
        self._update_layer_and_restart(event)

    def _on_ingress_ready_http(self, event: IngressPerAppReadyEvent):
        logger.info("Ingress for unit ready on '%s'", event.url)
        self._update_layer_and_restart(event)

    def _on_install(self, _):
        """Handler for the "install" event during which we will update the K8s service."""
        self.set_ports()

    def _update_layer_and_restart(self, _) -> None:
        """Define and start a workload using the Pebble API."""
        self.unit.status = MaintenanceStatus("Assembling pod spec")

        self.ingress_tcp.provide_ingress_requirements(
            scheme=urlparse(self.internal_url).scheme, port=self.config["ssh-port"]
        )
        self.ingress_http.provide_ingress_requirements(
            scheme=urlparse(self.internal_url).scheme, port=80
        )

        if self.container.can_connect():
            new_layer = self._pebble_layer.to_dict()

            if not self.container.exists("/etc/ssh/"):
                self._install_ssh_server()

            if not self.container.exists("/srv/Caddyfile"):
                current_caddyfile_config = self._generate_caddyfile_config()
                try:
                    self.container.push(
                        "/srv/Caddyfile",
                        current_caddyfile_config,
                        permissions=0o777,
                        make_dirs=True,
                    )
                    logger.info("Pushed caddyfile")
                except ConnectionError:
                    logger.error(
                        "Could not push datasource config. Pebble refused connection. Shutting down?"
                    )

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

    def _generate_caddyfile_config(self) -> str:
        config = """:80 {
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
        return config

    def _install_ssh_server(self):
        """Install the openssh server and the rsync server.

        This is temporary, in the future we should use a custom OCI image
        that will have prebaked ssh server and rsync installed.
        """
        ssh_port = self.config["ssh-port"]
        try:
            self.container.exec(["apk", "add", "openssh"]).wait()
            self.container.exec(
                ["sed", "-i", f"s/#Port 22/Port {ssh_port}/", "/etc/ssh/sshd_config"]
            )
            self.container.exec(["apk", "add", "openrc", "--no-cache"]).wait()
            self.container.exec(["apk", "add", "rsync"]).wait()
            self.container.exec(["rc-update", "add", "sshd"]).wait()
            self.container.exec(["ssh-keygen", "-A"]).wait()
            self.container.exec(["rc-status"]).wait()
            config = """"""
            self.container.push(
                "/run/openrc/softlevel",
                config,
                permissions=0o777,
                make_dirs=True,
            )
            self.container.exec(["/etc/init.d/sshd", "start"]).wait()
        except ExecError as e:
            print(f"Error: {e}")

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
    def _pebble_layer(self):
        """Return a dictionary representing a Pebble layer."""
        command = " ".join(["caddy", "run", "/srv/Caddyfile"])

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
