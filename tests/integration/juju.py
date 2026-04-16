#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Juju/Jubilant integration helpers."""

import json
from typing import List, Optional

import jubilant


def show_unit(juju: jubilant.Juju, unit: str) -> dict:
    """Return show-unit data for a unit."""
    output = juju.cli("show-unit", unit, "--format", "json")
    if isinstance(output, (tuple, list)):
        output = output[0]
    data = json.loads(output)
    if isinstance(data, dict) and unit in data:
        return data[unit]
    return data


def relation_application_data(
    juju: jubilant.Juju,
    unit: str,
    endpoint: str,
    related_unit: str,
    related_endpoint: str,
) -> List[dict]:
    """Return relation application-data entries for a unit relation."""
    unit_data = show_unit(juju, unit)
    data_items = []
    for rel in unit_data.get("relation-info", []):
        if rel.get("endpoint") != endpoint:
            continue
        if rel.get("related-endpoint") != related_endpoint:
            continue
        related_units = rel.get("related-units", {})
        if not isinstance(related_units, dict) or related_unit not in related_units:
            continue
        app_data = rel.get("application-data")
        if isinstance(app_data, dict) and app_data:
            data_items.append(app_data)
        related_app = rel.get("related-application")
        if isinstance(related_app, dict):
            related_app_data = related_app.get("application-data")
            if isinstance(related_app_data, dict) and related_app_data:
                data_items.append(related_app_data)
    return data_items


def get_ingress_url_from_unit(
    juju: jubilant.Juju,
    unit: str,
    endpoint: str,
    related_endpoint: str,
) -> str:
    """Return ingress URL from show-unit relation data."""

    def _extract_url(data: dict) -> Optional[str]:
        ingress_blob = data.get("ingress")
        if isinstance(ingress_blob, str) and ingress_blob:
            try:
                ingress_data = json.loads(ingress_blob)
            except json.JSONDecodeError:
                ingress_data = None
            if isinstance(ingress_data, dict):
                ingress_url = ingress_data.get("url")
                if isinstance(ingress_url, str) and ingress_url:
                    return ingress_url
        return None

    unit_data = show_unit(juju, unit)
    for rel in unit_data.get("relation-info", []):
        if rel.get("endpoint") != endpoint:
            continue
        if rel.get("related-endpoint") != related_endpoint:
            continue
        app_data = rel.get("application-data")
        if isinstance(app_data, dict):
            app_url = _extract_url(app_data)
            if app_url:
                return app_url

    raise RuntimeError(
        "Could not find ingress url in relation data for "
        f"unit={unit}, endpoint={endpoint}, related_endpoint={related_endpoint}. "
        f"unit_data={unit_data}"
    )
