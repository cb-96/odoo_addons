from odoo import fields
from odoo.tests.common import TransactionCase, HttpCase, tagged
from odoo.exceptions import AccessError
from ..journey_navigation import presentation, return_url, safe_destination


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
        self.rep.team_id = self.team
        task = self.env["federation.operation.task"].create({"name": "Other team private task", "task_type": "registration", "audience": "club",
            "responsible_club_id": self.club.id, "journey_team_id": self.other_team.id,
            "source_model": "federation.team", "source_record_id": self.other_team.id, "source_key": "journey_raw_other_team"})
        with self.assertRaises(AccessError):
            task.with_user(self.user).read(["name"])

    def test_team_scope_does_not_show_other_team(self):
        self.rep.team_id = self.team
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


@tagged("post_install", "-at_install", "sf_role_journeys", "sf_release_confidence")
class TestJourneyHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.user_admin").write({"group_ids": [(4, cls.env.ref("sports_federation_base.group_federation_manager").id)]})

    def test_role_home_renders_for_admin(self):
        self.authenticate("admin", "admin")
        response = self.url_open("/my/work")
        self.assertEqual(response.status_code, 200)
        self.assertIn("My federation work", response.text)

    def test_manager_queue_renders_replacement_template(self):
        self.authenticate("admin", "admin")
        response = self.url_open("/federation/action-items")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Manager work queue", response.text)

    def test_context_is_not_cached(self):
        self.authenticate("admin", "admin")
        response = self.url_open("/my/work/context")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.json()["user_id"], self.env.ref("base.user_admin").id)
