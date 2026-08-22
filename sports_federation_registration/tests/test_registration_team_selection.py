from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestRegistrationTeamSelection(TransactionCase):
    """Tests for the registration desk team selection rules."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Registration Selection Season",
                "date_start": "2025-09-01",
                "date_end": "2026-06-30",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Registration Selection Competition",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Registration Selection Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Senior Men Division",
                "edition_id": cls.edition.id,
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "date_start": "2025-10-01",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Registration Selection Club"}
        )
        cls.window = cls.env["federation.registration.window"].create(
            {
                "name": "Senior Men Registration",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
            }
        )

    def _make_team(self, name, category="senior", gender="male"):
        return self.env["federation.team"].create(
            {
                "name": name,
                "club_id": self.club.id,
                "category": category,
                "gender": gender,
            }
        )

    def test_available_teams_exclude_registered_and_mismatched_teams(self):
        eligible_team = self._make_team("Eligible Team")
        registered_team = self._make_team("Registered Team")
        wrong_gender_team = self._make_team(
            "Wrong Gender Team", gender="female"
        )
        wrong_category_team = self._make_team(
            "Wrong Category Team", category="junior"
        )
        self.env["federation.competition.entry"].create(
            {
                "window_id": self.window.id,
                "team_id": registered_team.id,
            }
        )

        entry = self.env["federation.competition.entry"].new(
            {"window_id": self.window.id}
        )
        entry._compute_available_team_ids()

        available_team_ids = entry.available_team_ids._origin.ids
        self.assertIn(eligible_team.id, available_team_ids)
        self.assertNotIn(registered_team.id, available_team_ids)
        self.assertNotIn(wrong_gender_team.id, available_team_ids)
        self.assertNotIn(wrong_category_team.id, available_team_ids)

    def test_invalid_gender_and_category_are_rejected_server_side(self):
        for name, category, gender in (
            ("Invalid Gender Team", "senior", "female"),
            ("Invalid Category Team", "junior", "male"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    self.env["federation.competition.entry"].create(
                        {
                            "window_id": self.window.id,
                            "team_id": self._make_team(
                                name, category=category, gender=gender
                            ).id,
                        }
                    )

    def test_onchange_returns_available_team_domain(self):
        eligible_team = self._make_team("Onchange Eligible Team")
        registered_team = self._make_team("Onchange Registered Team")
        self.env["federation.competition.entry"].create(
            {
                "window_id": self.window.id,
                "team_id": registered_team.id,
            }
        )

        entry = self.env["federation.competition.entry"].new(
            {"window_id": self.window.id}
        )
        result = entry._onchange_window_id()

        self.assertEqual(
            result["domain"]["team_id"],
            [("id", "in", entry.available_team_ids.ids)],
        )
        self.assertIn(eligible_team.id, entry.available_team_ids.ids)
        self.assertNotIn(registered_team.id, entry.available_team_ids.ids)