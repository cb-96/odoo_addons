from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_season_players")
class TestPlayerSeasonFees(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Annual Fee Club"})
        cls.season = cls.env["federation.season"].create({
            "name": "Annual Fee Season", "date_start": "2098-01-01",
            "date_end": "2098-12-31", "state": "open",
        })
        cls.player = cls.env["federation.player"].create({
            "first_name": "Annual", "last_name": "Fee", "club_id": cls.club.id,
            "gender": "male", "birth_date": "2000-01-01",
        })
        cls.registration = cls.env["federation.club.season.registration"]._get_or_create(cls.club, cls.season)
        cls.registration.billing_partner_id = cls.env["res.partner"].create({"name": "Annual Fee Customer"})
        cls.fee = cls.env.ref("sports_federation_finance_bridge.fee_type_player_season_registration")
        cls.fee.default_amount = 25

    def _events(self):
        return self.env["federation.finance.event"].search([
            ("source_model", "=", "federation.player.license"),
            ("source_res_id", "in", self.registration.license_ids.ids),
            ("fee_type_id", "=", self.fee.id),
        ])

    def test_approval_once_and_no_repricing(self):
        self.registration._add_players(self.player)
        self.assertFalse(self._events())
        self.registration.action_confirm()
        self.assertEqual(len(self._events()), 1)
        self.assertEqual(self._events().amount, 25)
        self.fee.default_amount = 50
        self.registration.action_confirm()
        self.registration.license_ids.action_activate()
        self.assertEqual(len(self._events()), 1)
        self.assertEqual(self._events().amount, 25)

    def test_zero_schedule_is_preserved(self):
        self.registration._add_players(self.player)
        self.registration.license_ids.category = "senior"
        self.env["federation.fee.schedule"].create({
            "fee_type_id": self.fee.id, "season_id": self.season.id,
            "category": "senior", "gender": "male", "amount": 0,
        })
        self.registration.action_confirm()
        self.assertEqual(self._events().amount, 0)

    def test_top_up_only_adds_one_charge(self):
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        second = self.player.copy({"first_name": "Second"})
        self.registration._add_players(second)
        self.registration.action_confirm()
        self.assertEqual(len(self._events()), 2)
        self.assertEqual(sum(self._events().mapped("amount")), 50)

    def test_new_season_team_fee_is_opt_in(self):
        self.assertFalse(self.season.team_registration_fee_enabled)

    def test_missing_billing_contact_rolls_back_approval(self):
        self.registration.billing_partner_id = False
        self.registration._add_players(self.player)
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.registration.action_confirm()
        self.assertEqual(self.registration.license_ids.state, "draft")
        self.assertFalse(self._events())

    def test_cancel_retains_original_charge(self):
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        event = self._events()
        self.registration.action_cancel()
        self.assertEqual(self._events(), event)
        self.assertEqual(event.amount, 25)

    def test_company_cannot_change_after_charge(self):
        from odoo.exceptions import ValidationError
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        other = self.env["res.company"].create({"name": "Other Annual Billing Company"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.registration.write({"company_id": other.id})
