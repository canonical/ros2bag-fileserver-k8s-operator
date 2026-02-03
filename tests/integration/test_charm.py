#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import requests
import yaml
from charmed_kubeflow_chisme.testing.cos_integration import (
    PROVIDES,
    _get_app_relation_data,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

CHARMCRAFT_YAML = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = CHARMCRAFT_YAML["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {
        "caddy-fileserver-image": CHARMCRAFT_YAML["resources"]["caddy-fileserver-image"][
            "upstream-source"
        ]
    }

    # Deploy the charm and wait for active/idle status
    await asyncio.gather(
        ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME),
        ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=1000
        ),
    )


@pytest.mark.abort_on_fail
async def test_connectivity(ops_test: OpsTest):
    status = await ops_test.model.get_status()
    address = status.applications[APP_NAME].units[APP_NAME + "/0"].address
    appurl = f"http://{address}:80/"
    r = requests.get(appurl)
    assert r.status_code == 200


async def test_integrate_blackbox(ops_test: OpsTest):
    # @todo: upgrade to stable when blackbox charm with probes relation
    # is promoted from edge.
    await ops_test.model.deploy(
        "blackbox-exporter-k8s", "blackbox", channel="latest/edge", trust=True
    )

    logger.info(
        "Adding relation: %s:%s",
        APP_NAME,
        "probes",
    )

    await ops_test.model.integrate(
        f"{APP_NAME}",
        "blackbox:probes",
    )

    await ops_test.model.wait_for_idle(
        apps=[
            f"{APP_NAME}",
            "blackbox",
        ],
        status="active",
    )


async def test_blackbox(ops_test: OpsTest):
    """Test probes are defined in relation data bag."""
    app = ops_test.model.applications[APP_NAME]

    relation_data = await _get_app_relation_data(app, "probes", side=PROVIDES)

    assert relation_data.get("scrape_metadata")
    assert relation_data.get("scrape_probes")
