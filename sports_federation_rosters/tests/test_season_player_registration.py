from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_season_players")
class TestMandatorySeasonPlayers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Roster Annual Club"})
        cls.team = cls.env["federation.team"].create({"name": "Annual Team", "club_id": cls.club.id})
        cls.season = cls.env["federation.season"].create({
            "name": "Roster Annual Season", "date_start": "2098-01-01",
            "date_end": "2098-12-31", "state": "open",
        })
        cls.player = cls.env["federation.player"].create({
            "first_name": "Roster", "last_name": "Annual", "club_id": cls.club.id,
            "gender": "male", "birth_date": "2000-01-01",
        })
        cls.roster = cls.env["federation.team.roster"].create({
            "team_id": cls.team.id, "season_id": cls.season.id,
        })
        cls.registration = cls.env["federation.club.season.registration"]._get_or_create(cls.club, cls.season)

    def _line(self):
        return self.env["federation.team.roster.line"].create({
            "roster_id": self.roster.id, "player_id": self.player.id,
        })

    def test_missing_registration_blocked_without_rule_set(self):
        self.assertFalse(self.roster.rule_set_id)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._line()

    def test_pending_registration_blocked(self):
        self.registration._add_players(self.player)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._line()

    def test_approved_registration_allowed_and_cancellation_rechecked(self):
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        line = self._line()
        self.assertTrue(line.eligible)
        self.registration.license_ids.action_cancel()
        self.assertTrue(line._get_eligibility_reasons())
        self.assertFalse(line.eligible)

    def test_wrong_season_blocked(self):
        other = self.env["federation.season"].create({
            "name": "Other Annual Season", "date_start": "2099-01-01",
            "date_end": "2099-12-31", "state": "open",
        })
        registration = self.env["federation.club.season.registration"]._get_or_create(self.club, other)
        registration._add_players(self.player)
        registration.action_confirm()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._line()

    def test_expired_registration_blocked(self):
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        self.registration.license_ids.write({"issue_date": "2097-01-01", "expiry_date": "2097-12-31"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._line()

    def test_roster_scope_change_cannot_bypass_registration(self):
        self.registration._add_players(self.player)
        self.registration.action_confirm()
        self._line()
        other = self.env["federation.season"].create({
            "name": "Scope Change Season", "date_start": "2099-01-01",
            "date_end": "2099-12-31", "state": "open",
        })
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.roster.write({"season_id": other.id})

    def test_wrong_club_registration_blocked(self):
        other_club = self.env["federation.club"].create({"name": "Wrong Licence Club"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["federation.player.license"].create({
                "player_id": self.player.id, "club_id": other_club.id,
                "season_id": self.season.id, "state": "active",
                "issue_date": "2098-01-01", "expiry_date": "2098-12-31",
            })
