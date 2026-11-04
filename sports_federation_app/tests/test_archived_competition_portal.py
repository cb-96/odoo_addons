from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_app")
class TestArchivedCompetitionPortal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wizard = cls.env["federation.practice.competition.wizard"].create(
            {
                "name": "Archive scope",
                "division_count": 1,
                "teams_per_division": 4,
                "gameday_count": 1,
                "first_gameday_today": False,
                "first_gameday": fields.Date.context_today(cls.env.user) + timedelta(days=30),
            }
        )
        wizard.action_create()
        cls.edition = cls.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] Archive scope")], limit=1
        )
        cls.division = cls.edition.tournament_ids[:1]
        cls.match = cls.env["federation.match"].search(
            [("tournament_id", "=", cls.division.id)], limit=1
        )
        cls.duty = cls.env["federation.match.club.referee.duty"].create(
            {
                "match_id": cls.match.id,
                "club_id": cls.match.home_team_id.club_id.id,
                "state": "open",
            }
        )
        cls.privilege = cls.env["federation.portal.privilege"]
        cls.scope = cls.env["federation.portal.archive.scope"]
        cls.Task = cls.env["federation.operation.task"]

    def _duty_tasks(self):
        return self.Task.search(
            [("source_model", "=", self.duty._name), ("source_record_id", "=", self.duty.id)]
        )

    def test_archiving_closes_tasks_and_sync_does_not_recreate_them(self):
        self.Task.sync_for_user(self.env.user)
        task = self._duty_tasks()
        self.assertTrue(task)
        self.assertNotEqual(task.state, "done")

        self.edition.write({"active": False})
        self.assertEqual(task.state, "done")
        self.Task.sync_for_user(self.env.user)
        self.assertEqual(self._duty_tasks().state, "done")
        self.assertFalse(
            self.privilege.portal_search(self.Task, [("id", "=", task.id)]),
            "a closed task of an archived competition is not shown as completed either",
        )

        self.edition.write({"active": True})
        self.Task.sync_for_user(self.env.user)
        self.assertNotEqual(self._duty_tasks().state, "done")

    def test_portal_reads_exclude_archived_competitions(self):
        day = self.env["federation.matchday"].search(
            [("edition_id", "=", self.edition.id)], limit=1
        )
        records = [self.match, self.duty, day]
        for record in records:
            self.assertTrue(self.privilege.portal_search(record, [("id", "=", record.id)]))

        self.edition.write({"active": False})
        for record in records:
            self.assertFalse(
                self.privilege.portal_search(record, [("id", "=", record.id)]),
                record._name,
            )
            self.assertEqual(
                self.privilege.portal_search_count(record, [("id", "=", record.id)]), 0
            )
        with self.assertRaises(AccessError):
            self.scope.assert_visible(self.duty)
        with self.assertRaises(AccessError):
            self.privilege.portal_assert_in_domain(self.match, [], "denied")

    def test_archiving_only_a_division_hides_its_records(self):
        self.division.with_context(active_test=False).write({"active": False})
        self.assertFalse(self.scope.filter_visible(self.match))
        self.assertTrue(self.edition.active)

    def test_unrelated_models_are_not_filtered(self):
        self.edition.write({"active": False})
        self.assertEqual(self.scope.exclusion_domain("federation.player"), [])
        team = self.match.home_team_id
        self.assertTrue(self.privilege.portal_search(team, [("id", "=", team.id)]))
