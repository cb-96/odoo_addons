from pathlib import Path
import re

ROUTE_PATTERN = re.compile(
    r"^\|\s*`(?P<method>GET|POST)\s+(?P<path>[^`]+)`\s*\|\s*`(?P<owner_module>[^`]+)`\s*\|"
)
INVENTORY_PATH = Path(__file__).resolve().parents[2] / "ROUTE_INVENTORY.md"


def load_route_inventory(owner_module=None):
    """Return route entries parsed from the markdown inventory."""
    routes = []
    for line in INVENTORY_PATH.read_text(encoding="utf-8").splitlines():
        match = ROUTE_PATTERN.match(line.strip())
        if not match:
            continue
        entry = match.groupdict()
        if owner_module and entry["owner_module"] != owner_module:
            continue
        routes.append(entry)
    return routes
