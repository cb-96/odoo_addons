from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestReportCatalog(TransactionCase):
    def test_catalog_uses_product_facing_categories(self):
        selection = dict(
            self.env["federation.report.catalog"]._fields["category"].selection
        )
        self.assertEqual(
            set(selection),
            {"operations", "competition", "people", "assurance", "finance", "audit"},
        )
