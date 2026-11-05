from datetime import datetime

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_task_deadlines")
class TestTaskDeadlines(TransactionCase):
    """Roster, line-up and registration work carries the date it becomes blocking."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.user = env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Deadline representative",
                "login": "deadline_rep_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [env.ref("sports_federation_portal.group_federation_portal_club").id],
                    )
                ],
            }
        )
        cls.club = env["federation.club"].create(
            {"name": "Deadline club", "code": "DLC"}
        )
        role = env["federation.club.role.type"].create(
            {"name": "Deadline role", "code": "deadline_test_role"}
        )
        env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": role.id,
            }
        )
        cls.season = env["federation.season"].create(
            {
                "name": "Deadline season",
                "code": "DLS",
                "date_start": "2030-01-01",
                "date_end": "2030-12-31",
            }
        )
        cls.competition = env["federation.competition"].create(
            {"name": "Deadline competition", "code": "DLCMP"}
        )
        cls.other_competition = env["federation.competition"].create(
            {"name": "Deadline other competition", "code": "DLCMP2"}
        )
        cls.tournament = env["federation.tournament"].create(
            {
                "name": "Deadline division",
                "code": "DLTOUR",
                "season_id": cls.season.id,
                "competition_id": cls.competition.id,
                "date_start": "2030-09-01",
            }
        )
        cls.Task = env["federation.operation.task"]

    def _team(self, code):
        return self.env["federation.team"].create(
            {"name": "Deadline team %s" % code, "club_id": self.club.id, "code": code}
        )

    def _participant(self, team, state="confirmed"):
        return self.env["federation.tournament.participant"].create(
            {"tournament_id": self.tournament.id, "team_id": team.id, "state": state}
        )

    def _match(self, team, kickoff, auto_sheets=False):
        Match = self.env["federation.match"]
        if not auto_sheets:
            Match = Match.with_context(skip_auto_match_sheets=True)
        return Match.create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": team.id,
                "date_scheduled": kickoff,
            }
        )

    def _deadline(self, team, competition=None):
        key = (team.id, self.season.id, competition.id if competition else 0)
        return self.Task._prefetch_roster_deadlines({}, [key])[key]

    # ── the roster deadline itself ───────────────────────────────────────

    def test_deadline_is_a_week_before_the_tournament_starts(self):
        team = self._team("DLT-A")
        self._participant(team)

        self.assertEqual(self._deadline(team), datetime(2030, 8, 25))

    def test_first_scheduled_match_decides_the_deadline(self):
        team = self._team("DLT-B")
        self._match(team, "2030-09-10 10:00:00")

        self.assertEqual(self._deadline(team), datetime(2030, 9, 3))

    def test_no_deadline_without_a_tournament(self):
        self.assertFalse(self._deadline(self._team("DLT-C")))

    def test_withdrawn_participant_has_no_deadline(self):
        team = self._team("DLT-D")
        self._participant(team, state="withdrawn")

        self.assertFalse(self._deadline(team))

    def test_deadline_respects_the_competition_scope(self):
        team = self._team("DLT-E")
        self._participant(team)

        self.assertEqual(self._deadline(team, self.competition), datetime(2030, 8, 25))
        self.assertFalse(self._deadline(team, self.other_competition))

    def test_cache_resolves_many_teams_together(self):
        first, second = self._team("DLT-F"), self._team("DLT-G")
        self._participant(first)
        keys = [(first.id, self.season.id, 0), (second.id, self.season.id, 0)]

        cache = self.Task._prefetch_roster_deadlines({}, keys)

        self.assertEqual(cache[keys[0]], datetime(2030, 8, 25))
        self.assertFalse(cache[keys[1]])

    # ── the tasks that carry it ──────────────────────────────────────────

    def _task(self, source, task_type):
        self.Task.sync_for_user(self.user)
        return self.Task.search(
            [
                ("source_model", "=", source._name),
                ("source_record_id", "=", source.id),
                ("task_type", "=", task_type),
            ]
        )

    def test_roster_readiness_task_carries_the_roster_deadline(self):
        team = self._team("DLT-H")
        self._participant(team)
        roster = self.env["federation.team.roster"].search(
            [("team_id", "=", team.id), ("season_id", "=", self.season.id)]
        )
        self.assertEqual(len(roster), 1)

        task = self._task(roster, "roster_readiness")

        self.assertEqual(len(task), 1)
        self.assertEqual(task.deadline, datetime(2030, 8, 25))

    def test_missing_roster_task_carries_the_roster_deadline(self):
        team = self._team("DLT-I")
        registration = self.env["federation.season.registration"].create(
            {"team_id": team.id, "season_id": self.season.id}
        )
        registration.action_confirm()
        self._match(team, "2030-09-10 10:00:00")
        self.assertFalse(
            self.env["federation.team.roster"].search_count(
                [("team_id", "=", team.id), ("season_id", "=", self.season.id)]
            )
        )

        task = self._task(registration, "roster_readiness")

        self.assertEqual(len(task), 1)
        self.assertEqual(task.deadline, datetime(2030, 9, 3))

    def test_lineup_task_is_due_when_the_game_day_starts(self):
        team = self._team("DLT-J")
        match = self._match(team, "2030-09-10 10:00:00", auto_sheets=True)
        sheet = self.env["federation.match.sheet"].search(
            [("match_id", "=", match.id), ("team_id", "=", team.id)]
        )
        self.assertEqual(len(sheet), 1)

        task = self._task(sheet, "gameday_lineup")

        self.assertEqual(len(task), 1)
        self.assertEqual(
            task.deadline, fields.Datetime.to_datetime("2030-09-10 10:00:00")
        )
