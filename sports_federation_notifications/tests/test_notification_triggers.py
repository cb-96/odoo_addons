from odoo.tests.common import TransactionCase


class TestNotificationTriggers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Trigger Club",
                "code": "TRIGC",
                "email": "trigger.club@example.com",
            }
        )
        cls.away_club = cls.env["federation.club"].create(
            {
                "name": "Trigger Away Club",
                "code": "TRIGA",
                "email": "trigger.away@example.com",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Trigger Team",
                "club_id": cls.club.id,
                "code": "TRIGT",
                "email": "trigger.team@example.com",
            }
        )
        cls.away_team = cls.env["federation.team"].create(
            {
                "name": "Trigger Away Team",
                "club_id": cls.away_club.id,
                "code": "TRIGAT",
                "email": "trigger.away.team@example.com",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Trigger Season",
                "code": "TRIGS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Trigger Tournament",
                "code": "TRIGTOUR",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team.id,
                "away_team_id": cls.away_team.id,
                "home_score": 2,
                "away_score": 1,
                "state": "done",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Trigger Rules",
                "code": "TRIGRULES",
            }
        )
        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "Trigger Standing",
                "tournament_id": cls.tournament.id,
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Trigger Referee",
                "email": "trigger.referee@example.com",
                "certification_level": "national",
            }
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Trigger Finance Fee",
                "code": "TRIGFIN",
                "category": "other",
                "default_amount": 45.0,
            }
        )
        cls.finance_event = cls.env["federation.finance.event"].create(
            {
                "name": "Trigger Finance Event",
                "fee_type_id": cls.fee_type.id,
                "event_type": "charge",
                "amount": 45.0,
                "source_model": "federation.club",
                "source_res_id": cls.club.id,
                "club_id": cls.club.id,
            }
        )
        cls.validator_group = cls.env.ref(
            "sports_federation_result_control.group_result_validator"
        )
        cls.approver_group = cls.env.ref(
            "sports_federation_result_control.group_result_approver"
        )
        cls.manager_group = cls.env.ref(
            "sports_federation_base.group_federation_manager"
        )
        cls.federation_user_group = cls.env.ref(
            "sports_federation_base.group_federation_user"
        )
        cls.submit_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Trigger Submit User",
                    "login": "trigger.submit@example.com",
                    "email": "trigger.submit@example.com",
                    "group_ids": [(6, 0, [cls.manager_group.id])],
                }
            )
        )
        cls.validator_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Trigger Validator",
                    "login": "trigger.validator@example.com",
                    "email": "trigger.validator@example.com",
                    "group_ids": [
                        (6, 0, [cls.manager_group.id, cls.validator_group.id])
                    ],
                }
            )
        )
        cls.approver_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Trigger Approver",
                    "login": "trigger.approver@example.com",
                    "email": "trigger.approver@example.com",
                    "group_ids": [
                        (6, 0, [cls.manager_group.id, cls.approver_group.id])
                    ],
                }
            )
        )

    def _create_active_roster(self, team):
        """Exercise create active roster."""
        player = self.env["federation.player"].create(
            {
                "first_name": team.code,
                "last_name": "Roster Player",
                "gender": "male",
            }
        )
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": f"{team.name} Trigger Roster Rules",
                "code": f"TRR{team.id}",
                "squad_min_size": 1,
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "name": f"{team.name} Trigger Roster",
                "team_id": team.id,
                "season_id": self.season.id,
                "rule_set_id": rule_set.id,
            }
        )
        self.env["federation.team.roster.line"].create(
            {
                "roster_id": roster.id,
                "player_id": player.id,
            }
        )
        roster.action_activate()
        return roster

    def test_participant_confirm_action_creates_notification_log(self):
        """Test that participant confirm action creates notification log."""
        self._create_active_roster(self.team)
        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
            }
        )

        participant.action_confirm()

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.tournament.participant"),
                ("target_res_id", "=", participant.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_participant_confirmed",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))

    def test_tournament_published_write_creates_notification_log(self):
        """Test that tournament published write creates notification log."""
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
            }
        )

        self.tournament.write({"website_published": True})

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.tournament"),
                ("target_res_id", "=", self.tournament.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_tournament_published",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))

    def test_referee_assignment_create_creates_notification_log(self):
        """Test that referee assignment create creates notification log."""
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.match.referee"),
                ("target_res_id", "=", assignment.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_referee_assigned",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))

    def test_result_approval_workflow_creates_result_logs(self):
        """Test that result approval workflow creates result logs."""
        match = self.match.with_user(self.submit_user)
        match.action_submit_result()
        self.match.invalidate_recordset()
        self.match.with_user(self.validator_user).action_verify_result()
        self.match.invalidate_recordset()
        self.match.with_user(self.approver_user).action_approve_result()

        activity_log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.match"),
                ("target_res_id", "=", self.match.id),
                ("notification_type", "=", "activity"),
                ("name", "=", f"Verify result: {self.match.name}"),
            ],
            limit=1,
        )
        approval_log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.match"),
                ("target_res_id", "=", self.match.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_result_approved",
                ),
            ],
            limit=1,
        )
        self.assertTrue(activity_log)
        self.assertIn(activity_log.state, ("sent", "failed"))
        self.assertTrue(approval_log)
        self.assertIn(approval_log.state, ("sent", "failed"))

    def test_standing_freeze_creates_notification_log(self):
        """Test that standing freeze creates notification log."""
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
            }
        )

        self.standing.action_freeze()

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.standing"),
                ("target_res_id", "=", self.standing.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_standing_frozen",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))

    def test_finance_event_confirm_creates_notification_log(self):
        """Test that finance event confirm creates notification log."""
        self.finance_event.action_confirm()

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.finance.event"),
                ("target_res_id", "=", self.finance_event.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_finance_confirmed",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))
