#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pathlib

import yaml

METADATA = yaml.safe_load(pathlib.Path("./charmcraft.yaml").read_text(encoding="utf-8"))
APP_NAME = METADATA["name"]

APP_BLACKBOX_ENDPOINT = "blackbox-probes"
APP_AUTH_DEVICES_KEYS_ENDPOINT = "auth-devices-keys"
APP_INGRESS_HTTP_ENDPOINT = "ingress-http"
APP_INGRESS_TCP_ENDPOINT = "ingress-tcp"

BLACKBOX_APP = "blackbox"
BLACKBOX_CHARM = "blackbox-exporter-k8s"
BLACKBOX_CHANNEL = "1/stable"
BLACKBOX_PROBES_ENDPOINT = "probes"

COS_REGISTRATION_SERVER_APP = "cos-registration-server"
COS_REGISTRATION_SERVER_CHARM = "cos-registration-server-k8s"
COS_REGISTRATION_SERVER_CHANNEL = "latest/edge"
COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT = "auth-devices-keys"
COS_REGISTRATION_SERVER_DATABASE_ENDPOINT = "database"
COS_REGISTRATION_SERVER_INGRESS_ENDPOINT = "ingress"

POSTGRESQL_APP = "postgresql"
POSTGRESQL_CHARM = "postgresql-k8s"
POSTGRESQL_CHANNEL = "14/stable"
POSTGRESQL_DATABASE_ENDPOINT = "database"

TRAEFIK_APP = "traefik"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_CHANNEL = "latest/stable"
TRAEFIK_INGRESS_ENDPOINT = "ingress"
TRAEFIK_INGRESS_PER_UNIT_ENDPOINT = "ingress-per-unit"
