from pathlib import Path

from odoo.tests.common import TransactionCase


class TestProductionSecurityMatrix(TransactionCase):
    """Static release contracts complement the existing HTTP ownership matrix."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_root = Path(__file__).resolve().parents[1]

    def test_mutating_portal_routes_declare_post_and_csrf(self):
        violations = []
        for path in sorted((self.portal_root / "controllers").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            chunks = source.split("@http.route(")[1:]
            for chunk in chunks:
                declaration = chunk.split(")\n", 1)[0]
                if 'methods=["POST"]' in declaration and "csrf=True" not in declaration:
                    violations.append(path.name)
        self.assertFalse(
            violations, "POST routes missing explicit CSRF: %s" % violations
        )

    def test_qol_bulk_routes_require_manager_group(self):
        source = (self.portal_root / "controllers" / "qol.py").read_text(
            encoding="utf-8"
        )
        for route in (
            "/federation/operations/bulk-registrations",
            "/federation/operations/send-reminders",
        ):
            route_index = source.index(route)
            method_body = source[route_index : route_index + 1200]
            self.assertIn("group_federation_manager", method_body)

    def test_portal_privilege_requires_explicit_scope(self):
        source = (self.portal_root / "models" / "portal_privilege.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("scope_domain", source)
        self.assertIn("portal_call", source)
        self.assertIn("portal_write", source)
