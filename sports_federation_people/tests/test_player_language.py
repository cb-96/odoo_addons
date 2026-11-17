from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_translations")
class TestPlayerLanguage(TransactionCase):
    def test_player_language_falls_back_to_the_federation(self):
        self.env["res.lang"]._activate_lang("fr_BE")
        self.env.company.partner_id.lang = "en_US"
        player = self.env["federation.player"].create(
            {"first_name": "Lang", "last_name": "Player"}
        )
        self.assertEqual(player._communication_lang(), "en_US")
        player.lang = "fr_BE"
        self.assertEqual(player._communication_lang(), "fr_BE")
