from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_planner_unresolved_fixtures")
class TestPlannerUnresolvedFixtures(TransactionCase):
    """The Hub counts the matches the match board can place, nothing more.

    A fixture with only one side resolved (a bye or "#1 Top vs TBD" that waits
    for progression) cannot be scheduled and is not offered on the match board.
    It must not keep the Hub on "Plan all N matches on game days".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Unresolved Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Unresolved Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Unresolved Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Unresolved Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        club = cls.env["federation.club"].create({"name": "Unresolved Club"})
        cls.teams = cls.env["federation.team"].create(
            [
                {"name": "Unresolved Team %s" % index, "club_id": club.id}
                for index in range(1, 5)
            ]
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "Unresolved Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Unresolved Format",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        league = cls.env["federation.structure.stage"].create(
            {
                "name": "Unresolved League",
                "structure_id": cls.structure.id,
                "stage_type": "league",
                "format_type": "manual",
                "source_type": "manual",
            }
        )
        finals = cls.env["federation.structure.stage"].create(
            {
                "name": "Unresolved Finals",
                "structure_id": cls.structure.id,
                "stage_type": "knockout",
                "format_type": "knockout",
                "source_type": "progression",
                "graph_state": "waiting",
            }
        )
        Fixture = cls.env["federation.fixture"]
        cls.playable = Fixture.create(
            {
                "structure_id": cls.structure.id,
                "stage_id": league.id,
                "round_number": 1,
                "home_team_id": cls.teams[0].id,
                "away_team_id": cls.teams[1].id,
                "state": "ready",
            }
        )
        # One incoming seed and no opponent or source: not schedulable yet.
        cls.placeholder = Fixture.create(
            {
                "structure_id": cls.structure.id,
                "stage_id": finals.id,
                "round_number": 1,
                "home_source_seed": 1,
                "state": "ready",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Unresolved Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Unresolved Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
            }
        )

    def _allocate(self, fixtures):
        self.env["federation.matchday.allocation"].create(
            {
                "matchday_id": self.matchday.id,
                "structure_id": self.structure.id,
                "manual_only": True,
                "manual_fixture_ids": [fields.Command.set(fixtures.ids)],
            }
        )

    def _issue_keys(self, expected):
        edition = self.edition.sudo()
        issues = edition._planner_global_issues(
            self.matchday, self.env["federation.schedule"], expected
        )
        return [issue["key"] for issue in issues]

    def test_placeholder_is_not_schedulable(self):
        self.assertTrue(self.playable._is_schedulable())
        self.assertFalse(self.placeholder._is_schedulable())

    def test_unresolved_placeholder_is_not_counted_as_unallocated(self):
        self._allocate(self.playable)
        keys = self._issue_keys(self.playable | self.placeholder)
        self.assertNotIn("unallocated-fixtures", keys)

    def test_unallocated_playable_match_still_blocks(self):
        # Nothing is allocated: the playable match must still be reported, and
        # only that one.
        edition = self.edition.sudo()
        issues = edition._planner_global_issues(
            self.matchday,
            self.env["federation.schedule"],
            self.playable | self.placeholder,
        )
        blocker = next(i for i in issues if i["key"] == "unallocated-fixtures")
        self.assertIn("1", blocker["message"])

    def test_planner_hub_has_no_allocation_blocker_when_all_playable_are_placed(self):
        self._allocate(self.playable)
        data = self.edition.get_competition_planner_data()
        self.assertNotIn(
            "unallocated-fixtures", [issue["key"] for issue in data["issues"]]
        )
