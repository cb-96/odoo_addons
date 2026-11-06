from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestDivisionScope(TransactionCase):
    def _practice(self, **values):
        wizard = self.env["federation.practice.competition.wizard"].create(
            dict(
                {
                    "name": "Scope %s" % self.id(),
                    "division_count": 2,
                    "teams_per_division": 4,
                    "gameday_count": 3,
                    "first_gameday_today": False,
                    "first_gameday": fields.Date.context_today(self.env.user) + timedelta(days=30),
                },
                **values,
            )
        )
        wizard.action_create()
        return self.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] %s" % wizard.name)], limit=1
        )

    def test_workspace_divisions_follow_the_competition_lifecycle(self):
        edition = self._practice()
        self.assertEqual(edition.state, "open")
        for division in edition.tournament_ids:
            self.assertTrue(division.has_workspace_format)
            self.assertFalse(division.stage_ids, "no legacy stages are needed")
            self.assertIn("matches", division.format_stage_summary or "")
            self.assertEqual(division.state, "open")
        edition.transition_competition_state("in_progress")
        self.assertEqual(set(edition.tournament_ids.mapped("state")), {"in_progress"})

    def test_start_accepts_a_frozen_format_instead_of_legacy_stages(self):
        edition = self._practice(division_count=1)
        division = edition.tournament_ids
        self.assertEqual(division.state, "open")
        division.action_start()
        self.assertEqual(division.state, "in_progress")

    def test_game_days_only_receive_matches_of_their_divisions(self):
        edition = self._practice()
        first, second = edition.tournament_ids.sorted("id")
        days = self.env["federation.matchday"].search(
            [("edition_id", "=", edition.id)], order="date,id"
        )
        fixtures = self.env["federation.fixture"].search(
            [("edition_id", "=", edition.id), ("state", "!=", "cancelled")]
        )
        capacities = [
            {"matchday_id": days[0].id, "date": days[0].date, "capacity": 100,
             "division_ids": first.ids},
            {"matchday_id": days[1].id, "date": days[1].date, "capacity": 100,
             "division_ids": second.ids},
        ]
        proposal = self.env["federation.competition.schedule.distributor"].propose(
            fixtures, capacities
        )
        self.assertFalse(proposal["errors"], proposal["errors"])
        by_id = {fixture.id: fixture for fixture in fixtures}
        for fixture_id in proposal["assignments"].get(days[0].id, []):
            self.assertEqual(by_id[fixture_id].division_id, first)
        for fixture_id in proposal["assignments"].get(days[1].id, []):
            self.assertEqual(by_id[fixture_id].division_id, second)

    def test_division_without_a_game_day_is_reported_by_name(self):
        edition = self._practice()
        first, second = edition.tournament_ids.sorted("id")
        day = self.env["federation.matchday"].search(
            [("edition_id", "=", edition.id)], order="date,id", limit=1
        )
        fixtures = self.env["federation.fixture"].search([("edition_id", "=", edition.id)])
        proposal = self.env["federation.competition.schedule.distributor"].propose(
            fixtures,
            [{"matchday_id": day.id, "date": day.date, "capacity": 100,
              "division_ids": first.ids}],
        )
        self.assertTrue(any(second.display_name in error for error in proposal["errors"]))

    def test_teams_and_format_sets_category_and_gender_and_filters_teams(self):
        edition = self._practice(division_count=1)
        wizard = self.env["federation.competition.division.setup.wizard"].create(
            {"edition_id": edition.id}
        )
        line = wizard.line_ids[:1]
        self.assertTrue(line)
        line.write({"category": "senior", "gender": "female"})
        self.assertFalse(
            line.eligible_team_ids.filtered(lambda team: team.gender != "female")
        )

    def test_creation_wizard_keeps_division_category_and_gender(self):
        season = self.env["federation.season"].create(
            {"name": "Scope season", "date_start": "2030-07-01", "date_end": "2031-06-30"}
        )
        creation = self.env["federation.create.competition.wizard"].create(
            {
                "name": "Scope gendered league",
                "season_id": season.id,
                "date_start": "2030-09-01",
                "date_end": "2031-05-01",
                "division_line_ids": [
                    (0, 0, {"name": "Men", "category": "senior", "gender": "male"}),
                    (0, 0, {"name": "Mixed", "category": "senior", "gender": "mixed"}),
                ],
            }
        )
        creation.action_create_competition()
        self.assertTrue(creation.competition_id)
        self.assertTrue(creation.season_id)
        edition = self.env["federation.competition.edition"].search(
            [("name", "=", "Scope gendered league")], limit=1
        )
        genders = dict(edition.tournament_ids.mapped(lambda d: (d.name, d.gender)))
        self.assertEqual(genders, {"Men": "male", "Mixed": "mixed"})
