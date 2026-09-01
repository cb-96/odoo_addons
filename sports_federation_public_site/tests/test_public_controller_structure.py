from pathlib import Path

from odoo.tests.common import TransactionCase


class TestPublicControllerStructure(TransactionCase):
    def test_request_infrastructure_is_extracted_from_route_controller(self):
        root = Path(__file__).resolve().parents[1] / "controllers"
        controller = (root / "public_competitions.py").read_text()
        helper = (root / "_public_request.py").read_text()
        self.assertIn("PublicRequestInfrastructureMixin", controller)
        self.assertNotIn("def _get_rate_limit_subject", controller)
        self.assertIn("def _get_rate_limit_subject", helper)
