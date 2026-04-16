#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import requests

from tests.integration.constants import (
    APP_AUTH_DEVICES_KEYS_ENDPOINT,
    APP_BLACKBOX_ENDPOINT,
    APP_NAME,
    BLACKBOX_APP,
    BLACKBOX_PROBES_ENDPOINT,
    COS_REGISTRATION_SERVER_APP,
    COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT,
    COS_REGISTRATION_SERVER_INGRESS_ENDPOINT,
    POSTGRESQL_APP,
    TRAEFIK_APP,
    TRAEFIK_INGRESS_ENDPOINT,
)
from tests.integration.juju import get_ingress_url_from_unit, relation_application_data

logger = logging.getLogger(__name__)


def wait_for_active_idle_without_error(juju: jubilant.Juju, timeout: int = 60 * 45):
    """Wait for the model to settle without errors."""
    logger.info(f"waiting for the model ({juju.model}) to settle ...")
    # grafana_agent_app stays in blocked state by design
    juju.wait(
        ready=lambda status: jubilant.all_active(
            status,
            APP_NAME,
            BLACKBOX_APP,
            COS_REGISTRATION_SERVER_APP,
            POSTGRESQL_APP,
            TRAEFIK_APP,
        ),
        delay=10,
        timeout=timeout,
        error=jubilant.any_error,
    )
    logger.info("waiting for agents idle ...")
    juju.wait(
        jubilant.all_agents_idle,
        delay=10,
        timeout=timeout,
        error=lambda status: jubilant.any_error(
            status,
            APP_NAME,
            BLACKBOX_APP,
            COS_REGISTRATION_SERVER_APP,
            POSTGRESQL_APP,
            TRAEFIK_APP,
        ),
    )


def test_deploy(juju):
    """Assert deployment of charm-under-test reaches active status."""
    wait_for_active_idle_without_error(juju)


def test_blackbox(juju):
    """Test probes are defined in relation data bag."""
    app_unit = f"{APP_NAME}/0"
    blackbox_unit = f"{BLACKBOX_APP}/0"
    relation_data = relation_application_data(
        juju,
        blackbox_unit,
        BLACKBOX_PROBES_ENDPOINT,
        app_unit,
        APP_BLACKBOX_ENDPOINT,
    )
    assert relation_data
    assert relation_data[0].get("scrape_metadata")
    assert relation_data[0].get("scrape_probes")


def test_auth_devices_keys_propagates_from_cos_registration_server(juju):
    """Add a fake device and verify auth key appears in relation data."""
    cos_registration_server_api_url = (
        get_ingress_url_from_unit(
            juju,
            unit=f"{COS_REGISTRATION_SERVER_APP}/0",
            endpoint=COS_REGISTRATION_SERVER_INGRESS_ENDPOINT,
            related_endpoint=TRAEFIK_INGRESS_ENDPOINT,
        )
        + "/api/v1/devices/"
    )
    device_uid = "robot-1"
    public_ssh_key = (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDitestfakekey integration-test@localhost"
    )

    response = requests.post(
        cos_registration_server_api_url,
        json={
            "uid": device_uid,
            "address": "10.1.2.3",
            "public_ssh_key": public_ssh_key,
        },
        timeout=30,
    )
    assert response.status_code in (200, 201), response.text

    app_unit = f"{APP_NAME}/0"
    cos_registration_server_unit = f"{COS_REGISTRATION_SERVER_APP}/0"

    def key_available(_) -> bool:
        relation_entries = relation_application_data(
            juju,
            app_unit,
            APP_AUTH_DEVICES_KEYS_ENDPOINT,
            cos_registration_server_unit,
            COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT,
        )
        if not relation_entries:
            return False
        payload = relation_entries[0].get("auth_devices_keys", "")
        return device_uid in payload and public_ssh_key in payload

    juju.wait(ready=key_available, delay=5, timeout=300, error=jubilant.any_error)

    relation_data = relation_application_data(
        juju,
        app_unit,
        APP_AUTH_DEVICES_KEYS_ENDPOINT,
        cos_registration_server_unit,
        COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT,
    )
    assert relation_data
    assert device_uid in relation_data[0].get("auth_devices_keys", "")
    assert public_ssh_key in relation_data[0].get("auth_devices_keys", "")
