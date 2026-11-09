from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_portal_translations")
class TestPortalTranslations(TransactionCase):
    """The Dutch and French portal translations load and apply."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for code in ("nl_BE", "fr_BE"):
            cls.env["res.lang"]._activate_lang(code)
        cls.env["ir.module.module"]._load_module_terms(
            ["sports_federation_portal", "sports_federation_rosters"],
            ["nl_BE", "fr_BE"],
            overwrite=True,
        )

    def test_template_terms_are_translated(self):
        view = self.env.ref("sports_federation_portal.player_availability_link_invalid")
        self.assertIn("Deze link werkt niet", view.with_context(lang="nl_BE").arch_db)
        self.assertIn("Ce lien ne fonctionne pas", view.with_context(lang="fr_BE").arch_db)

    def test_code_terms_are_translated(self):
        other = self.env["federation.club"].create(
            {"name": "Translation Club", "code": "TRC"}
        )
        user = self.env["res.users"].create(
            {"name": "Translation User", "login": "translation.user@example.com"}
        )
        Club = self.env["federation.club"].with_context(lang="nl_BE")
        with self.assertRaisesRegex(AccessError, "Alleen vertegenwoordigers"):
            Club._portal_set_player_availability(other.id, True, user=user)

    def test_selection_labels_are_translated(self):
        field = self.env["federation.player.availability"]._fields["response"]
        labels = dict(field._description_selection(self.env(context={"lang": "fr_BE"})))
        self.assertEqual(labels["no"], "Indisponible")
