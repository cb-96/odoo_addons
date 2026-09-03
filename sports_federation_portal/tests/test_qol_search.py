from odoo.tests import TransactionCase


class TestQolSearch(TransactionCase):
    def test_short_queries_return_no_results(self):
        self.assertEqual(self.env["federation.qol.search"].search_everywhere("x"), [])

    def test_search_returns_typed_direct_links(self):
        team = self.env["federation.team"].create({"name": "Unique Search Team"})
        results = self.env["federation.qol.search"].search_everywhere("Unique Search")
        match = next(item for item in results if item["model"] == "federation.team")
        self.assertEqual(match["name"], team.display_name)
        self.assertIn(str(team.id), match["url"])
        self.assertTrue(match["type"])
