from odoo.tests.common import TransactionCase


class TestFederationOperationTasks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_group = cls.env.ref(
            "sports_federation_base.group_federation_manager"
        )
        cls.manager = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Action Queue Manager",
                    "login": "action.queue.manager@example.com",
                    "group_ids": [(6, 0, [cls.manager_group.id])],
                }
            )
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Action Queue Club", "code": "AQC"}
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Action Queue Team",
                "club_id": cls.club.id,
                "code": "AQCT",
                "category": "senior",
                "gender": "mixed",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Action Queue Season",
                "code": "AQS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Action Queue Tournament",
                "code": "AQT",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
                "state": "open",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {"name": "Action Queue Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Action Queue Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
            }
        )
        cls.tournament.write(
            {
                "edition_id": cls.edition.id,
                "competition_id": cls.competition.id,
            }
        )
        cls.window = cls.env["federation.registration.window"].create(
            {
                "name": "Action Queue Window",
                "edition_id": cls.edition.id,
                "division_id": cls.tournament.id,
                "state": "open",
            }
        )

    def test_blocking_task_cannot_be_manually_acknowledged(self):
        task = self.env["federation.operation.task"].create(
            {
                "name": "Blocking readiness task",
                "task_type": "roster_readiness",
                "audience": "manager",
                "blocking": True,
                "source_model": "test.source",
                "source_record_id": 1,
                "source_key": "test.source:1:roster_readiness",
            }
        )
        with self.assertRaisesRegex(Exception, "Blocking tasks"):
            task.action_acknowledge()

    def test_operation_task_opens_its_owning_record(self):
        task = self.env["federation.operation.task"].create(
            {
                "name": "Open source",
                "task_type": "registration",
                "audience": "manager",
                "source_model": self.window._name,
                "source_record_id": self.window.id,
                "source_key": f"{self.window._name}:{self.window.id}:open",
            }
        )
        action = task.action_open_source()
        self.assertEqual(action["res_model"], self.window._name)
        self.assertEqual(action["res_id"], self.window.id)

    def test_result_queue_identifies_required_workflow_role(self):
        away_club = self.env["federation.club"].create({"name": "Queue Away Club"})
        away_team = self.env["federation.team"].create(
            {"name": "Queue Away Team", "club_id": away_club.id}
        )
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team.id,
                "away_team_id": away_team.id,
                "home_score": 1,
                "away_score": 0,
                "state": "done",
                "result_state": "submitted",
            }
        )

        self.env["federation.operation.task"].sync_for_user(user=self.manager)
        task = self.env["federation.operation.task"].search(
            [("match_id", "=", match.id), ("state", "!=", "done")], limit=1
        )

        self.assertTrue(task)
        self.assertEqual(task.task_type, "result_review")
        self.assertEqual(task.required_role, "result_verifier")
        self.assertEqual(task.next_step, "Verify result")

    def test_parental_consent_uses_the_existing_action_projection(self):
        player = self.env["federation.player"].create(
            {
                "name": "Action Queue Minor",
                "first_name": "Action",
                "last_name": "Minor",
                "birth_date": "2012-01-01",
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": self.competition.id,
            }
        )
        approval = self.env["federation.player.parental.approval"].create(
            {
                "player_id": player.id,
                "guardian_name": "Action Queue Guardian",
                "approval_date": "2020-01-01",
                "valid_until": "2030-01-01",
                "approval_document": b"c2lnbmVk",
            }
        )
        approval.action_verify()
        line = self.env["federation.team.roster.line"].create(
            {"roster_id": roster.id, "player_id": player.id}
        )
        approval.revocation_reason = "Consent withdrawn"
        approval.action_revoke()

        self.env["federation.operation.task"].sync_for_user(user=self.manager)
        task = self.env["federation.operation.task"].search(
            [
                ("task_type", "=", "parental_consent"),
                ("source_model", "=", line._name),
                ("source_record_id", "=", line.id),
                ("state", "!=", "done"),
            ],
            limit=1,
        )

        self.assertTrue(task)
        self.assertEqual(task.priority, "2")
        self.assertEqual(
            task.action_open_source()["res_model"],
            "federation.player.parental.approval",
        )

    def test_shared_gameday_lineup_projects_one_task_per_team_and_day(self):
        away_club = self.env["federation.club"].create({"name": "Lineup Away Club"})
        away_team = self.env["federation.team"].create(
            {"name": "Lineup Away Team", "club_id": away_club.id}
        )
        for kickoff in ("2025-06-01 10:00:00", "2025-06-01 14:00:00"):
            self.env["federation.match"].create(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": self.team.id,
                    "away_team_id": away_team.id,
                    "date_scheduled": kickoff,
                    "state": "scheduled",
                }
            )

        self.env["federation.operation.task"].sync_for_user(user=self.manager)
        tasks = self.env["federation.operation.task"].search(
            [
                ("task_type", "=", "gameday_lineup"),
                ("responsible_club_id", "=", self.club.id),
                ("state", "!=", "done"),
            ]
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks.source_model, "federation.match.sheet")
