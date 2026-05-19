from odoo.addons.sports_federation_base.tests.route_inventory import (
    load_route_inventory,
)
from odoo.tests.common import TransactionCase


class TestRouteInventory(TransactionCase):
    def test_route_inventory_owner_modules_are_smoke_backed(self):
        owner_modules = {entry["owner_module"] for entry in load_route_inventory()}

        self.assertEqual(
            owner_modules,
            {
                "sports_federation_portal",
                "sports_federation_public_site",
                "sports_federation_compliance",
                "sports_federation_reporting",
                "sports_federation_import_tools",
            },
        )

    def test_route_inventory_has_unique_http_entries(self):
        routes = [(entry["method"], entry["path"]) for entry in load_route_inventory()]

        self.assertEqual(len(routes), len(set(routes)))
