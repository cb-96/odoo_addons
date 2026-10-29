from odoo import SUPERUSER_ID, api, fields
from odoo.tests.common import TransactionCase, HttpCase, tagged
from odoo.exceptions import AccessError, ValidationError
from ..controllers.role_journeys import RoleJourneys
from ..journey_navigation import presentation, return_url, reviewer_can_act, safe_destination


@tagged("post_install", "-at_install", "sf_role_journeys", "sf_release_confidence")
class TestJourneyTasks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Journey representative", "login": "journey_rep_test",
            "group_ids": [(6, 0, [cls.env.ref("sports_federation_portal.group_federation_portal_club").id])],
        })
        cls.club = cls.env["federation.club"].create({"name": "Journey club", "code": "JRC"})
        cls.team = cls.env["federation.team"].create({"name": "Journey team", "code": "JRT", "club_id": cls.club.id})
        cls.other_team = cls.env["federation.team"].create({"name": "Other journey team", "code": "JRO", "club_id": cls.club.id})
        cls.role = cls.env["federation.club.role.type"].create({"name": "Journey role", "code": "journey_test_role"})
        cls.rep = cls.env["federation.club.representative"].create({
            "club_id": cls.club.id, "partner_id": cls.user.partner_id.id,
            "user_id": cls.user.id, "role_type_id": cls.role.id,
        })
        cls.season = cls.env["federation.season"].create({"name": "Journey season", "code": "JRS", "date_start": "2026-01-01", "date_end": "2026-12-31"})
        cls.registration = cls.env["federation.season.registration"].create({"team_id": cls.team.id, "season_id": cls.season.id})
        cls.registration.action_confirm()

    def _scope_rep_to_team(self):
        scoped_role = self.env["federation.club.role.type"].create({
            "name": "Journey team-scoped role", "code": "journey_test_team_role",
            "team_scoped": True,
        })
        self.rep.write({"role_type_id": scoped_role.id, "team_id": self.team.id})

    def test_missing_roster_sync_does_not_create_source(self):
        Task = self.env["federation.operation.task"]
        before = self.env["federation.team.roster"].search_count([("team_id", "=", self.team.id)])
        Task.sync_for_user(self.user)
        tasks = Task.search([("source_model", "=", self.registration._name), ("source_record_id", "=", self.registration.id)])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks.journey_team_id, self.team)
        self.assertEqual(tasks.action_url, "/my/work/registrations/%s" % self.registration.id)
        self.assertEqual(self.env["federation.team.roster"].search_count([("team_id", "=", self.team.id)]), before)

    def test_refresh_keeps_identity_and_completion_timestamp(self):
        Task = self.env["federation.operation.task"]
        Task.sync_for_user(self.user)
        task = Task.search([("source_model", "=", self.registration._name), ("source_record_id", "=", self.registration.id)], limit=1)
        original = task.id
        Task.sync_for_user(self.user)
        self.assertEqual(task.id, original)
        self.assertEqual(task.state, "open")
        self.assertFalse(task.completed_on)

    def test_roster_creation_resolves_missing_task(self):
        Task = self.env["federation.operation.task"]
        Task.sync_for_user(self.user)
        task = Task.search([("source_model", "=", self.registration._name), ("source_record_id", "=", self.registration.id)], limit=1)
        self.env["federation.team.roster"]._portal_create_roster_for_registration(self.registration, user=self.user)
        Task.sync_for_user(self.user)
        self.assertEqual(task.state, "done")
        self.assertEqual(task.journey_status, "completed")

    def test_completed_timestamp_is_not_rewritten_by_refresh(self):
        Task = self.env["federation.operation.task"]
        Task.sync_for_user(self.user)
        task = Task.search([("source_model", "=", self.registration._name), ("source_record_id", "=", self.registration.id)], limit=1)
        self.env["federation.team.roster"]._portal_create_roster_for_registration(self.registration, user=self.user)
        Task.sync_for_user(self.user)
        completed = task.completed_on
        Task.sync_for_user(self.user)
        self.assertEqual(task.completed_on, completed)

    def test_raw_task_read_respects_team_scope(self):
        self._scope_rep_to_team()
        task = self.env["federation.operation.task"].create({"name": "Other team private task", "task_type": "registration", "audience": "club",
            "responsible_club_id": self.club.id, "journey_team_id": self.other_team.id,
            "source_model": "federation.team", "source_record_id": self.other_team.id, "source_key": "journey_raw_other_team"})
        with self.assertRaises(AccessError):
            task.with_user(self.user).read(["name"])

    def test_team_scope_does_not_show_other_team(self):
        self._scope_rep_to_team()
        Task = self.env["federation.operation.task"]
        Task.sync_for_user(self.user)
        Task.create({"name": "Other team work", "task_type": "registration", "audience": "club",
                     "responsible_club_id": self.club.id, "journey_team_id": self.other_team.id,
                     "source_model": "federation.team", "source_record_id": self.other_team.id, "source_key": "journey_other_team"})
        visible = Task.sudo().search(Task._portal_get_domain(self.user))
        self.assertNotIn(self.other_team, visible.mapped("journey_team_id"))

    def test_expired_representative_has_no_club_scope(self):
        self.rep.write({"date_start": "1999-01-01", "date_end": "2000-01-01"})
        self.assertNotIn(self.club.id, self.env["federation.operation.task"]._portal_club_ids(self.user))

    def test_unknown_source_not_ready(self):
        task = self.env["federation.operation.task"].create({"name": "Unknown source", "task_type": "registration", "audience": "club",
            "source_model": "journey.missing", "source_record_id": 1, "source_key": "journey_missing"})
        self.assertEqual(task.journey_status, "unavailable")
        self.assertEqual(task.journey_owner, "unknown")

    def test_acknowledged_is_not_completed(self):
        self.assertEqual(presentation("acknowledged", "club", "federation.team", "present")[0], "actionable")

    def test_source_action_rechecks_actual_access(self):
        task = self.env["federation.operation.task"].create({"name": "Private source", "task_type": "registration", "audience": "club",
            "responsible_club_id": self.club.id, "source_model": "res.users", "source_record_id": self.env.ref("base.user_admin").id, "source_key": "journey_private"})
        with self.assertRaises(AccessError):
            task.with_user(self.user).action_open_source()

    def test_source_projection_checks_portal_scope_not_sudo_visibility(self):
        Task = self.env["federation.operation.task"]
        visible = Task.create({"name": "My registration", "task_type": "roster_readiness", "audience": "club",
            "responsible_club_id": self.club.id, "source_model": self.registration._name,
            "source_record_id": self.registration.id, "source_key": "journey_visible_registration"})
        hidden = Task.create({"name": "Private user source", "task_type": "registration", "audience": "club",
            "responsible_club_id": self.club.id, "source_model": "res.users",
            "source_record_id": self.env.ref("base.user_admin").id, "source_key": "journey_private_projection"})

        self.assertEqual(
            visible.with_context(journey_viewer_id=self.user.id).sudo().journey_status,
            "actionable",
        )
        self.assertEqual(
            hidden.with_context(journey_viewer_id=self.user.id).sudo().journey_status,
            "unavailable",
        )

    def test_team_task_assignment_rejects_another_team_representative(self):
        scoped_role = self.env["federation.club.role.type"].create({
            "name": "Journey team role", "code": "journey_team_role", "team_scoped": True,
        })
        other_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Other team representative", "login": "journey_other_team",
            "group_ids": [(6, 0, [self.env.ref("sports_federation_portal.group_federation_portal_club").id])],
        })
        self.env["federation.club.representative"].create({
            "club_id": self.club.id, "partner_id": other_user.partner_id.id,
            "user_id": other_user.id, "role_type_id": scoped_role.id,
            "team_id": self.other_team.id,
        })
        task = self.env["federation.operation.task"].create({
            "name": "Team-specific work", "task_type": "roster_readiness", "audience": "club",
            "responsible_club_id": self.club.id, "journey_team_id": self.team.id,
            "source_model": self.team._name, "source_record_id": self.team.id,
            "source_key": "journey_team_assignment_scope",
        })

        allowed_users = task._allowed_assignment_users()
        self.assertIn(self.user, allowed_users)
        self.assertNotIn(other_user, allowed_users)
        task.action_assign_user(self.user)
        self.assertEqual(task.assigned_user_id, self.user)
        with self.assertRaises(ValidationError):
            task.action_assign_user(other_user)

    def test_reviewer_visibility_obeys_independent_review_policy(self):
        user_id, submitter_id, verifier_id = 31, 31, 32
        self.assertFalse(reviewer_can_act("submitted", user_id, submitter_id, False))
        self.assertTrue(reviewer_can_act("submitted", user_id, submitter_id, False, self_verification_allowed=True))
        self.assertFalse(reviewer_can_act("verified", user_id, submitter_id, verifier_id))
        self.assertTrue(reviewer_can_act("verified", user_id, submitter_id, verifier_id, self_approval_allowed=True))
        self.assertFalse(reviewer_can_act("approved", user_id, submitter_id, verifier_id, self_approval_allowed=True))

    def test_review_queue_applies_edition_policy_to_real_match(self):
        competition = self.env["federation.competition"].create({
            "name": "Journey review competition", "competition_type": "league",
        })
        edition = self.env["federation.competition.edition"].create({
            "name": "Journey review edition", "competition_id": competition.id,
            "season_id": self.season.id, "result_self_verification_allowed": False,
            "result_self_approval_allowed": False,
        })
        rule_set = self.env["federation.rule.set"].create({
            "name": "Journey review rules", "code": "JRVR",
            "points_win": 3, "points_draw": 1, "points_loss": 0,
        })
        tournament = self.env["federation.tournament"].create({
            "name": "Journey review tournament", "code": "JRVT",
            "season_id": self.season.id, "competition_id": competition.id,
            "edition_id": edition.id, "date_start": "2026-01-01",
            "rule_set_id": rule_set.id,
        })
        self.env["federation.tournament.participant"].create([
            {"tournament_id": tournament.id, "team_id": self.team.id},
            {"tournament_id": tournament.id, "team_id": self.other_team.id},
        ])
        other_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Independent reviewer", "login": "journey_independent_reviewer",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        match = self.env["federation.match"].create({
            "tournament_id": tournament.id, "home_team_id": self.team.id,
            "away_team_id": self.other_team.id, "state": "done",
            "result_state": "submitted", "result_submitted_by_id": self.user.id,
        })

        self.env["federation.operation.task"]._journey_assert_source_access(
            match, self.user
        )
        self.assertFalse(RoleJourneys._can_review_match(match, self.user))
        self.assertTrue(RoleJourneys._can_review_match(match, other_user))
        match.write({
            "result_state": "verified", "result_submitted_by_id": other_user.id,
            "result_verified_by_id": self.user.id,
        })
        self.assertFalse(RoleJourneys._can_review_match(match, self.user))
        edition.write({"result_self_approval_allowed": True})
        self.assertTrue(RoleJourneys._can_review_match(match, self.user))


@tagged("post_install", "-at_install", "sf_role_journeys", "sf_release_confidence")
class TestJourneyHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            portal_group = env.ref("sports_federation_portal.group_federation_portal_club")
            official_group = env.ref("sports_federation_portal.group_federation_portal_official")
            internal_group = env.ref("base.group_user")

            def create_user(name, login, groups):
                return env["res.users"].with_context(no_reset_password=True).create({
                    "name": name, "login": login, "email": login,
                    "password": "journey-test-password",
                    "group_ids": [(6, 0, groups)],
                })

            cls.club_user = create_user("Journey Club User", "journey.club@example.test", [portal_group.id])
            cls.team_user = create_user("Journey Team User", "journey.team@example.test", [portal_group.id])
            cls.official_user = create_user("Journey Official User", "journey.official@example.test", [official_group.id])
            cls.planner_user = create_user("Journey Planner User", "journey.planner@example.test", [internal_group.id, env.ref("sports_federation_competition_core.group_competition_administrator").id])
            cls.reviewer_user = create_user("Journey Reviewer User", "journey.reviewer@example.test", [internal_group.id, env.ref("sports_federation_result_control.group_result_approver").id])
            cls.manager_user = create_user("Journey Manager User", "journey.manager@example.test", [internal_group.id, env.ref("sports_federation_base.group_federation_manager").id])

            club = env["federation.club"].create({"name": "Journey HTTP Club", "code": "JHCL"})
            team = env["federation.team"].create({"name": "Journey HTTP Team", "code": "JHTM", "club_id": club.id})
            other_team = env["federation.team"].create({"name": "Journey HTTP Other Team", "code": "JHOT", "club_id": club.id})
            club_role = env.ref("sports_federation_portal.role_type_competition_contact")
            env["federation.club.representative"].create({
                "club_id": club.id, "partner_id": cls.club_user.partner_id.id,
                "user_id": cls.club_user.id, "role_type_id": club_role.id,
            })
            team_role = env["federation.club.role.type"].create({
                "name": "Journey HTTP Team Role", "code": "journey_http_team_role", "team_scoped": True,
            })
            env["federation.club.representative"].create({
                "club_id": club.id, "partner_id": cls.team_user.partner_id.id,
                "user_id": cls.team_user.id, "role_type_id": team_role.id, "team_id": team.id,
            })
            env["federation.referee"].create({
                "name": "Journey HTTP Referee", "email": cls.official_user.email,
                "certification_level": "national", "user_id": cls.official_user.id,
            })
            season = env["federation.season"].create({
                "name": "Journey HTTP Season", "code": "JHSE",
                "date_start": "2026-01-01", "date_end": "2026-12-31",
            })
            registration = env["federation.season.registration"].create({
                "team_id": team.id, "season_id": season.id, "user_id": cls.team_user.id,
            })
            registration.action_confirm()
            env["federation.operation.task"].create({
                "name": "Other team must stay hidden", "task_type": "roster_readiness",
                "audience": "club", "responsible_club_id": club.id,
                "journey_team_id": other_team.id, "source_model": other_team._name,
                "source_record_id": other_team.id, "source_key": "journey_http_other_team",
            })
            cr.commit()

    def test_role_home_renders_for_ordinary_role_users(self):
        roles = (
            ("journey.club@example.test", "Club and team preparation"),
            ("journey.team@example.test", "Club and team preparation"),
            ("journey.official@example.test", "My official assignments"),
            ("journey.planner@example.test", "Competition planning"),
            ("journey.reviewer@example.test", "Result review"),
            ("journey.manager@example.test", "Organising and review"),
        )
        for login, expected in roles:
            with self.subTest(role=login):
                self.authenticate(login, "journey-test-password")
                response = self.url_open("/my/work")
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected, response.text)

    def test_manager_queue_renders_replacement_template(self):
        self.authenticate("journey.manager@example.test", "journey-test-password")
        response = self.url_open("/federation/operations/action-items")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Manager work queue", response.text)

    def test_team_manager_inbox_hides_other_team(self):
        self.authenticate("journey.team@example.test", "journey-test-password")
        response = self.url_open("/my/action-items?scope=club")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Journey HTTP Team", response.text)
        self.assertNotIn("Other team must stay hidden", response.text)

    def test_official_assignment_list_renders_for_portal_official(self):
        self.authenticate("journey.official@example.test", "journey-test-password")
        response = self.url_open("/my/referee-assignments?filterby=history")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Internal Server Error", response.text)

    def test_review_queue_renders_for_reviewer_without_admin(self):
        self.authenticate("journey.reviewer@example.test", "journey-test-password")
        response = self.url_open("/my/work/reviews")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Result review", response.text)

    def test_context_is_not_cached(self):
        self.authenticate("journey.club@example.test", "journey-test-password")
        response = self.url_open("/my/work/context")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.json()["user_id"], self.club_user.id)
