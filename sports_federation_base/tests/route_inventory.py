"""Loader for the governed HTTP-route contract.

The route contract is deliberately stored as JSON instead of being extracted
from ROUTE_INVENTORY.md. The Markdown document explains ownership and review
policy; this registry is the stable machine-readable source used by tests.
"""

import json
from pathlib import Path

_REQUIRED_FIELDS = {"method", "path", "owner_module", "coverage_key"}
_ALLOWED_METHODS = {"DELETE", "GET", "PATCH", "POST", "PUT"}


def _inventory_path():
    return (
        Path(__file__).resolve().parents[2]
        / "ci"
        / "contracts"
        / "route_inventory.json"
    )


def _validated_routes(payload):
    if payload.get("schema_version") != 1:
        raise AssertionError("Unsupported route inventory schema version.")
    routes = payload.get("routes")
    if not isinstance(routes, list):
        raise AssertionError("Route inventory must contain a routes list.")

    normalized = []
    identities = set()
    coverage_keys = set()
    for index, raw_entry in enumerate(routes, start=1):
        if not isinstance(raw_entry, dict):
            raise AssertionError(f"Route inventory entry {index} must be an object.")
        missing = _REQUIRED_FIELDS - set(raw_entry)
        if missing:
            raise AssertionError(
                f"Route inventory entry {index} is missing: {', '.join(sorted(missing))}."
            )
        entry = {key: str(raw_entry[key]).strip() for key in _REQUIRED_FIELDS}
        entry["method"] = entry["method"].upper()
        if entry["method"] not in _ALLOWED_METHODS:
            raise AssertionError(f"Unsupported route method: {entry['method']}.")
        if not entry["path"].startswith("/"):
            raise AssertionError(f"Route path must start with '/': {entry['path']}.")
        if not entry["owner_module"].startswith("sports_federation_"):
            raise AssertionError(
                f"Route owner must be a federation addon: {entry['owner_module']}."
            )
        identity = (entry["method"], entry["path"])
        if identity in identities:
            raise AssertionError(f"Duplicate governed route: {identity}.")
        if entry["coverage_key"] in coverage_keys:
            raise AssertionError(
                f"Duplicate route smoke coverage key: {entry['coverage_key']}."
            )
        identities.add(identity)
        coverage_keys.add(entry["coverage_key"])
        normalized.append(entry)
    return normalized


def load_route_inventory(owner_module=None):
    """Return validated governed routes, optionally scoped to one owner addon."""
    path = _inventory_path()
    if not path.is_file():
        raise AssertionError(f"Route inventory contract is missing: {path}.")
    with path.open(encoding="utf-8") as inventory_file:
        routes = _validated_routes(json.load(inventory_file))
    if owner_module:
        routes = [entry for entry in routes if entry["owner_module"] == owner_module]
    return routes
