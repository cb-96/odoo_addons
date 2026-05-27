import unittest

from odoo.tests.common import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestWorkspaceVenueConstraints(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "federation.competition.workspace.service" not in cls.env.registry:
            raise unittest.SkipTest(
                "sports_federation_competition_engine not installed."
            )

        cls.service = cls.env["federation.competition.workspace.service"]
        cls.club = cls.env["federation.club"].create(
            {"name": "Venue Workspace Club", "code": "VWC"}
        )
        cls.teams = cls.env["federation.team"]
        for index in range(1, 5):
            cls.teams |= cls.env["federation.team"].create(
                {
                    "name": f"Venue Workspace Team {index}",
                    "club_id": cls.club.id,
                    "code": f"VWT{index}",
                }
            )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Venue Workspace Season",
                "code": "VWS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.competition_template = cls.env["federation.competition"].create(
            {
                "name": "Venue Workspace League",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Venue Workspace League 2026",
                "competition_id": cls.competition_template.id,
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
                "date_end": "2026-08-30",
            }
        )
        cls.venue = cls.env["federation.venue"].create(
            {"name": "Constraint Arena", "city": "Test City"}
        )
        cls.court = cls.env["federation.playing.area"].create(
            {"name": "Constraint Court", "venue_id": cls.venue.id}
        )

    def _prepare_planned_division(self, name):
        division = self.env["federation.tournament"].create(
            {
                "name": name,
                "edition_id": self.edition.id,
                "competition_id": self.competition_template.id,
                "season_id": self.season.id,
                "date_start": "2026-06-10",
                "date_end": "2026-06-10",
                "planning_format": "single_round_robin",
                "workspace_state": "registration_open",
            }
        )
        for seed, team in enumerate(self.teams, start=1):
            self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": division.id,
                    "team_id": team.id,
                    "seed": seed,
                    "state": "confirmed",
                }
            )
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Constraint Day",
                "round_date": "2026-06-10",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        self.service.generate_slots(
            gameday_id,
            [self.court.id],
            "09:00",
            "09:35",
            30,
            5,
            [],
            False,
        )
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        return division, gameday, division.match_ids[:1], gameday.slot_ids[:1]

    def test_blackout_window_blocks_gameday_validation_and_updates_summary(self):
        division, gameday, match, slot = self._prepare_planned_division(
            "Venue Blackout Division"
        )

        self.service.assign_match_to_slot(match.id, slot.id)
        self.env["federation.venue.blackout"].create(
            {
                "venue_id": self.venue.id,
                "playing_area_id": self.court.id,
                "date_start": slot.start_datetime,
                "date_end": slot.end_datetime,
                "closure_type": "blackout",
            }
        )

        validation = self.service.validate_gameday(gameday.id)
        planner = self.service.get_gameday_planner_data(gameday.id)

        self.assertIn(
            "venue_blackout",
            {issue["code"] for issue in validation["blocking"]},
        )
        self.assertEqual(planner["gameday"]["venue_summary"]["attention_match_count"], 1)
        self.assertEqual(planner["gameday"]["venue_summary"]["blackout_match_count"], 1)
        self.assertFalse(planner["gameday"]["venue_summary"]["clear_match_count"])

    def test_required_capability_blocks_assignment_until_court_matches(self):
        division, _gameday, match, slot = self._prepare_planned_division(
            "Venue Capability Division"
        )
        capability = self.env["federation.playing.area.capability"].create(
            {"name": "TV Lighting", "code": "TV-LIGHT"}
        )
        division.required_playing_area_capability_ids = [(6, 0, [capability.id])]

        validation = self.service.validate_match_assignment(match.id, slot.id)
        self.assertIn(
            "venue_capability_mismatch",
            {issue["code"] for issue in validation["blocking"]},
        )

        self.court.capability_ids = [(4, capability.id)]
        validation = self.service.validate_match_assignment(match.id, slot.id)
        self.assertNotIn(
            "venue_capability_mismatch",
            {issue["code"] for issue in validation["blocking"]},
        )