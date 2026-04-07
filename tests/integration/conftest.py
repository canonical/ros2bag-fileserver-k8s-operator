#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import pathlib
import subprocess
from collections.abc import Generator
from typing import Any, Dict

import jubilant
import pytest
import yaml

from tests.integration.constants import (
    APP_AUTH_DEVICES_KEYS_ENDPOINT,
    APP_BLACKBOX_ENDPOINT,
    APP_INGRESS_HTTP_ENDPOINT,
    APP_INGRESS_TCP_ENDPOINT,
    BLACKBOX_APP,
    BLACKBOX_CHANNEL,
    BLACKBOX_CHARM,
    BLACKBOX_PROBES_ENDPOINT,
    COS_REGISTRATION_SERVER_APP,
    COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT,
    COS_REGISTRATION_SERVER_CHANNEL,
    COS_REGISTRATION_SERVER_DATABASE_ENDPOINT,
    COS_REGISTRATION_SERVER_INGRESS_ENDPOINT,
    POSTGRESQL_APP,
    POSTGRESQL_CHANNEL,
    POSTGRESQL_DATABASE_ENDPOINT,
    TRAEFIK_APP,
    TRAEFIK_CHANNEL,
    TRAEFIK_CHARM,
    TRAEFIK_INGRESS_ENDPOINT,
    TRAEFIK_INGRESS_PER_UNIT_ENDPOINT,
)

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Pytest fixture wrapping Jubilant model lifecycle."""

    def show_debug_log(current_juju: jubilant.Juju):
        if request.session.testsfailed:
            print(current_juju.debug_log(limit=1000), end="")

    use_existing = _env_flag("JUJU_USE_EXISTING", default=False)
    if use_existing:
        current_juju = jubilant.Juju()
        yield current_juju
        show_debug_log(current_juju)
        return

    model = os.environ.get("JUJU_MODEL")
    if model:
        current_juju = jubilant.Juju(model=model)
        yield current_juju
        show_debug_log(current_juju)
        return

    keep_models = _env_flag("JUJU_KEEP_MODELS", default=False)
    with jubilant.temp_model(keep=keep_models) as current_juju:
        current_juju.wait_timeout = 10 * 60
        yield current_juju
        show_debug_log(current_juju)


@pytest.fixture(scope="session")
def metadata() -> Dict[str, Any]:
    """Provides charm metadata."""
    return yaml.safe_load(pathlib.Path("./charmcraft.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def charm_file(metadata: Dict[str, Any]) -> str:
    """Pack charm and return filename, or use CHARM_FILE if set."""
    charm_file_env = os.environ.get("CHARM_FILE")
    if charm_file_env:
        return charm_file_env

    try:
        subprocess.run(["charmcraft", "pack"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise OSError(f"Error packing charm: {exc}; stderr:\n{exc.stderr}") from None

    app_name = metadata["name"]
    repo_root = pathlib.Path(__file__).parent.parent.parent
    charms = [path.absolute() for path in repo_root.glob(f"{app_name}_*.charm")]
    assert charms, f"{app_name} .charm file not found"
    assert len(charms) == 1, f"{app_name} has more than one .charm file, unsure which to use"
    return str(charms[0])


@pytest.fixture(scope="module", autouse=True)
def app_fixture(juju: jubilant.Juju, metadata: Dict[str, Any], charm_file: str) -> str:
    """Builds and deploys the charm and its required relations/resources."""
    app_name = metadata["name"]
    resource_name = "caddy-fileserver-image"
    charm_oci_image = metadata["resources"][resource_name]["upstream-source"]

    juju.deploy(
        charm=charm_file,
        app=app_name,
        resources={resource_name: charm_oci_image},
    )

    juju.deploy(BLACKBOX_CHARM, app=BLACKBOX_APP, channel=BLACKBOX_CHANNEL, trust=True)
    juju.deploy(TRAEFIK_CHARM, app=TRAEFIK_APP, channel=TRAEFIK_CHANNEL, trust=True)

    juju.deploy(
        COS_REGISTRATION_SERVER_APP,
        app=COS_REGISTRATION_SERVER_APP,
        channel=COS_REGISTRATION_SERVER_CHANNEL,
        trust=True,
    )
    # required by cos-registration-server
    juju.deploy(POSTGRESQL_APP, app=POSTGRESQL_APP, channel=POSTGRESQL_CHANNEL, trust=True)

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        app_name,
        APP_BLACKBOX_ENDPOINT,
        BLACKBOX_APP,
        BLACKBOX_PROBES_ENDPOINT,
    )
    juju.integrate(
        f"{app_name}:{APP_BLACKBOX_ENDPOINT}",
        f"{BLACKBOX_APP}:{BLACKBOX_PROBES_ENDPOINT}",
    )

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        app_name,
        APP_INGRESS_HTTP_ENDPOINT,
        TRAEFIK_APP,
        TRAEFIK_INGRESS_ENDPOINT,
    )
    juju.integrate(
        f"{app_name}:{APP_INGRESS_HTTP_ENDPOINT}",
        f"{TRAEFIK_APP}:{TRAEFIK_INGRESS_ENDPOINT}",
    )

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        app_name,
        APP_INGRESS_TCP_ENDPOINT,
        TRAEFIK_APP,
        TRAEFIK_INGRESS_PER_UNIT_ENDPOINT,
    )
    juju.integrate(
        f"{app_name}:{APP_INGRESS_TCP_ENDPOINT}",
        f"{TRAEFIK_APP}:{TRAEFIK_INGRESS_PER_UNIT_ENDPOINT}",
    )

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        COS_REGISTRATION_SERVER_APP,
        COS_REGISTRATION_SERVER_DATABASE_ENDPOINT,
        POSTGRESQL_APP,
        POSTGRESQL_DATABASE_ENDPOINT,
    )
    juju.integrate(
        f"{COS_REGISTRATION_SERVER_APP}:{COS_REGISTRATION_SERVER_DATABASE_ENDPOINT}",
        f"{POSTGRESQL_APP}:{POSTGRESQL_DATABASE_ENDPOINT}",
    )

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        COS_REGISTRATION_SERVER_APP,
        COS_REGISTRATION_SERVER_INGRESS_ENDPOINT,
        TRAEFIK_APP,
        TRAEFIK_INGRESS_ENDPOINT,
    )
    juju.integrate(
        f"{COS_REGISTRATION_SERVER_APP}:{COS_REGISTRATION_SERVER_INGRESS_ENDPOINT}",
        f"{TRAEFIK_APP}:{TRAEFIK_INGRESS_ENDPOINT}",
    )

    logger.info(
        "Adding relation: %s:%s and %s:%s",
        app_name,
        APP_AUTH_DEVICES_KEYS_ENDPOINT,
        COS_REGISTRATION_SERVER_APP,
        COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT,
    )
    juju.integrate(
        f"{app_name}:{APP_AUTH_DEVICES_KEYS_ENDPOINT}",
        f"{COS_REGISTRATION_SERVER_APP}:{COS_REGISTRATION_SERVER_AUTH_DEVICES_KEYS_ENDPOINT}",
    )

    juju.wait(
        lambda status: jubilant.all_active(
            status,
            app_name,
            BLACKBOX_APP,
            COS_REGISTRATION_SERVER_APP,
            POSTGRESQL_APP,
            TRAEFIK_APP,
        ),
        timeout=3000,
    )
    return app_name
