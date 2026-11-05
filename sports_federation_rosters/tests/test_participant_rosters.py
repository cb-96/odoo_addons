from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_participant_rosters")
class TestParticipantRosters(TransactionCase):
    """A team that becomes a participant gets its roster, tied to its registration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.season = env["federation.season"].create(
            {
                "name": "Participant Roster Season",
                "code": "PRS-1",
                "date_start": "2030-01-01",
                "date_end": "2030-12-31",
            }
        )
        cls.competition = env["federation.competition"].create(
            {"name": "Participant Roster Competition", "code": "PRCMP-1"}
        )
        cls.other_competition = env["federation.competition"].create(
            {"name": "Participant Roster Other Competition", "code": "PRCMP-2"}
        )
        cls.club = env["federation.club"].create(
            {"name": "Participant Roster Club", "code": "PRC-1"}
        )
        cls.tournament = env["federation.tournament"].create(
            {
                "name": "Participant Roster Division",
                "code": "PRTOUR-1",
                "season_id": cls.season.id,
                "competition_id": cls.competition.id,
                "date_start": "2030-09-01",
            }
        )

    def _team(self, code):
        return self.env["federation.team"].create(
            {
                "name": "Participant Roster Team %s" % code,
                "club_id": self.club.id,
                "code": code,
            }
        )

    def _registration(self, team):
        registration = self.env["federation.season.registration"].create(
            {"season_id": self.season.id, "team_id": team.id}
        )
        registration.action_confirm()
        return registration

    def _rosters(self, team):
        return self.env["federation.team.roster"].search(
            [("team_id", "=", team.id), ("season_id", "=", self.season.id)]
        )

    def _participant(self, team):
        return self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": team.id,
                "state": "confirmed",
            }
        )

    def test_participant_roster_is_linked_to_the_confirmed_registration(self):
        team = self._team("PRT-A")
        registration = self._registration(team)

        self._participant(team)

        roster = self._rosters(team)
        self.assertEqual(len(roster), 1)
        self.assertEqual(roster.season_registration_id, registration)
        self.assertEqual(roster.competition_id, self.competition)

    def test_existing_unlinked_roster_is_linked_not_duplicated(self):
        team = self._team("PRT-B")
        registration = self._registration(team)
        existing = self.env["federation.team.roster"].create(
            {
                "team_id": team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )
        self.assertFalse(existing.season_registration_id)

        self._participant(team)

        self.assertEqual(self._rosters(team), existing)
        self.assertEqual(existing.season_registration_id, registration)

    def test_roster_without_a_confirmed_registration_stays_unlinked(self):
        team = self._team("PRT-C")

        self._participant(team)

        roster = self._rosters(team)
        self.assertEqual(len(roster), 1)
        self.assertFalse(roster.season_registration_id)

    def test_draft_registration_is_not_linked(self):
        team = self._team("PRT-D")
        self.env["federation.season.registration"].create(
            {"season_id": self.season.id, "team_id": team.id}
        )

        self._participant(team)

        self.assertFalse(self._rosters(team).season_registration_id)

    def test_season_baseline_prefers_open_generic_active_then_newest(self):
        team = self._team("PRT-E")
        Roster = self.env["federation.team.roster"]

        def make(competition, status="draft"):
            return Roster.create(
                {
                    "team_id": team.id,
                    "season_id": self.season.id,
                    "competition_id": competition.id if competition else False,
                    "status": status,
                }
            )

        closed_generic = make(False, "closed")
        draft_competition = make(self.competition)
        active_other = make(self.other_competition, "active")
        open_generic = make(False)
        pick = Roster._pick_season_baseline

        # Not closed beats closed, then generic beats competition-specific.
        self.assertEqual(
            pick(closed_generic | draft_competition | active_other | open_generic),
            open_generic,
        )
        # Among competition rosters the active one wins.
        self.assertEqual(
            pick(closed_generic | draft_competition | active_other), active_other
        )
        self.assertEqual(pick(closed_generic | draft_competition), draft_competition)
        # A closed roster is still found, so no second roster is created.
        self.assertEqual(pick(closed_generic), closed_generic)
        self.assertFalse(pick(Roster.browse()))
