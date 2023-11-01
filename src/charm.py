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
    HookEvent,
    RelationJoinedEvent,
)

from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer, ConnectionError

from charms.traefik_route_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.catalogue_k8s.v0.catalogue import CatalogueConsumer, CatalogueItem
import socket


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
        self.ingress = TraefikRouteRequirer(self, self.model.get_relation("ingress"), "ingress")  # type: ignore
        self.framework.observe(self.on["ingress"].relation_joined, self._configure_ingress)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.on.leader_elected, self._configure_ingress)
        self.framework.observe(self.on.config_changed, self._configure_ingress)

        self.framework.observe(
            self.on.ros2bag_fileserver_pebble_ready, self._update_layer_and_restart
        )

        self.catalog = CatalogueConsumer(
            charm=self,
            refresh_event=[
                self.on.ros2bag_fileserver_pebble_ready,
                self.ingress.on.ready,
                self.on["ingress"].relation_broken,
                self.on.config_changed,
            ],
            item=CatalogueItem(
                name="ros2bag fileserver",
                icon="graph-line-variant",
                url=self.external_url + "/",
                description=("ROS 2 bag fileserver to store robotics data."),
            ),
        )

    def _on_ingress_ready(self, _) -> None:
        """Once Traefik tells us our external URL, make sure we reconfigure the charm."""
        self._update_layer_and_restart(None)

    def _configure_ingress(self, event: HookEvent) -> None:
        """Set up ingress if a relation is joined, config changed, or a new leader election."""
        if not self.unit.is_leader():
            return

        # If it's a RelationJoinedEvent, set it in the ingress object
        if isinstance(event, RelationJoinedEvent):
            self.ingress._relation = event.relation

        # No matter what, check readiness -- this blindly checks whether `ingress._relation` is not
        # None, so it overlaps a little with the above, but works as expected on leader elections
        # and config-change
        if self.ingress.is_ready():
            self._update_layer_and_restart(None)
            self.ingress.submit_to_traefik(self._ingress_config)

    def _update_layer_and_restart(self, event) -> None:
        """Define and start a workload using the Pebble API."""
        self.unit.status = MaintenanceStatus("Assembling pod spec")
        if self.container.can_connect():
            new_layer = self._pebble_layer.to_dict()

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

    @property
    def _scheme(self) -> str:
        return "http"

    @property
    def internal_url(self) -> str:
        """Return workload's internal URL. Used for ingress."""
        return f"{self._scheme}://{socket.getfqdn()}:{80}"

    @property
    def external_url(self) -> str:
        """Return the external hostname configured, if any."""
        if self.ingress.external_host:
            path_prefix = f"{self.model.name}-{self.model.app.name}"
            return f"{self._scheme}://{self.ingress.external_host}/{path_prefix}"
        return self.internal_url

    @property
    def _ingress_config(self) -> dict:
        """Build a raw ingress configuration for Traefik."""
        # The path prefix is the same as in ingress per app
        external_path = f"{self.model.name}-{self.model.app.name}"

        middlewares = {
            f"juju-sidecar-trailing-slash-handler-{self.model.name}-{self.model.app.name}": {
                "redirectRegex": {
                    "regex": [f"^(.*)\\/{external_path}$"],
                    "replacement": [f"/{external_path}/"],
                    "permanent": True,
                }
            },
            f"juju-sidecar-noprefix-{self.model.name}-{self.model.app.name}": {
                "stripPrefix": {"forceSlash": False, "prefixes": [f"/{external_path}"]},
            },
        }

        routers = {
            "juju-{}-{}-router".format(self.model.name, self.model.app.name): {
                "entryPoints": ["web"],
                "rule": f"PathPrefix(`/{external_path}`)",
                "middlewares": list(middlewares.keys()),
                "service": "juju-{}-{}-service".format(self.model.name, self.app.name),
            },
            "juju-{}-{}-router-tls".format(self.model.name, self.model.app.name): {
                "entryPoints": ["websecure"],
                "rule": f"PathPrefix(`/{external_path}`)",
                "middlewares": list(middlewares.keys()),
                "service": "juju-{}-{}-service".format(self.model.name, self.app.name),
                "tls": {
                    "domains": [
                        {
                            "main": self.ingress.external_host,
                            "sans": [f"*.{self.ingress.external_host}"],
                        },
                    ],
                },
            },
        }

        services = {
            "juju-{}-{}-service".format(self.model.name, self.model.app.name): {
                "loadBalancer": {"servers": [{"url": self.internal_url}]}
            }
        }

        return {"http": {"routers": routers, "services": services, "middlewares": middlewares}}

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
