from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_roster_availability")
class TestRosterAvailability(TransactionCase):
    """One availability rule for the backend picker, the portal and saving."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Availability Club", "code": "AVC"}
        )
        Team = cls.env["federation.team"]
        cls.first = Team.create(
            {"name": "Availability First", "club_id": cls.club.id, "gender": "male"}
        )
        cls.second = Team.create(
            {"name": "Availability Second", "club_id": cls.club.id, "gender": "male"}
        )
        cls.other_division_team = Team.create(
            {"name": "Availability Other", "club_id": cls.club.id, "gender": "male"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Availability Season",
                "code": "AVS",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        Tournament = cls.env["federation.tournament"]
        division = Tournament.create(
            {
                "name": "Availability Division",
                "code": "AVD",
                "season_id": cls.season.id,
                "date_start": "2026-09-01",
            }
        )
        other_division = Tournament.create(
            {
                "name": "Availability Other Division",
                "code": "AVO",
                "season_id": cls.season.id,
                "date_start": "2026-09-01",
            }
        )
        Participant = cls.env["federation.tournament.participant"]
        for team in cls.first | cls.second:
            Participant.create({"tournament_id": division.id, "team_id": team.id})
        Participant.create(
            {"tournament_id": other_division.id, "team_id": cls.other_division_team.id}
        )
        Roster = cls.env["federation.team.roster"]
        cls.first_roster = Roster.create(
            {"team_id": cls.first.id, "season_id": cls.season.id}
        )
        cls.second_roster = Roster.create(
            {"team_id": cls.second.id, "season_id": cls.season.id}
        )
        cls.other_roster = Roster.create(
            {"team_id": cls.other_division_team.id, "season_id": cls.season.id}
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Avery",
                "last_name": "Available",
                "gender": "male",
                "club_id": cls.club.id,
            }
        )
        cls.env["federation.team.roster.line"].create(
            {"roster_id": cls.second_roster.id, "player_id": cls.player.id}
        )

    def test_player_on_the_roster_is_unavailable_there(self):
        self.assertIn(self.player, self.second_roster.unavailable_player_ids)

    def test_same_division_club_team_is_unavailable(self):
        self.assertIn(self.player, self.first_roster.unavailable_player_ids)
        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"].create(
                {"roster_id": self.first_roster.id, "player_id": self.player.id}
            )

    def test_other_division_is_not_affected(self):
        self.assertNotIn(self.player, self.other_roster.unavailable_player_ids)
        self.env["federation.team.roster.line"].create(
            {"roster_id": self.other_roster.id, "player_id": self.player.id}
        )

    def test_withdrawn_participation_does_not_count(self):
        self.env["federation.tournament.participant"].search(
            [("team_id", "=", self.first.id)]
        ).write({"state": "withdrawn"})
        self.first_roster.invalidate_recordset(["same_division_player_ids"])
        self.assertNotIn(self.player, self.first_roster.same_division_player_ids)
