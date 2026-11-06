from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
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
                "first_gameday": fields.Date.context_today(cls.env.user)
                + timedelta(days=30),
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
            [
                ("source_model", "=", self.duty._name),
                ("source_record_id", "=", self.duty.id),
            ]
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
            self.assertTrue(
                self.privilege.portal_search(record, [("id", "=", record.id)])
            )

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


@tagged("post_install", "-at_install", "sf_app")
class TestArchivedCompetitionRosters(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wizard = cls.env["federation.practice.competition.wizard"].create(
            {
                "name": "Archive rosters",
                "division_count": 1,
                "teams_per_division": 4,
                "gameday_count": 1,
                "first_gameday_today": False,
                "first_gameday": fields.Date.context_today(cls.env.user)
                + timedelta(days=30),
            }
        )
        wizard.action_create()
        cls.edition = cls.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] Archive rosters")], limit=1
        )
        cls.division = cls.edition.tournament_ids[:1]
        cls.team = (
            cls.env["federation.match"]
            .search([("tournament_id", "=", cls.division.id)], limit=1)
            .home_team_id
        )
        cls.season = cls.division.season_id or cls.edition.season_id
        cls.roster = cls.env["federation.team.roster"].create(
            {
                "name": "Archive roster",
                "team_id": cls.team.id,
                "season_id": cls.season.id,
            }
        )
        cls.scope = cls.env["federation.portal.archive.scope"]
        cls.privilege = cls.env["federation.portal.privilege"]

    def _visible(self, record):
        return bool(self.privilege.portal_search(record, [("id", "=", record.id)]))

    def test_roster_is_hidden_when_its_only_competition_is_archived(self):
        self.assertTrue(self._visible(self.roster))
        self.edition.write({"active": False})
        self.assertIn(self.roster.id, self.scope.hidden_roster_ids())
        self.assertFalse(self._visible(self.roster))
        with self.assertRaises(AccessError):
            self.scope.assert_visible(self.roster)
        self.edition.write({"active": True})
        self.assertTrue(self._visible(self.roster))

    def test_roster_stays_when_the_team_still_plays_an_active_competition(self):
        other_competition = self.env["federation.competition"].create(
            {"name": "Archive rosters other"}
        )
        other = self.env["federation.competition.edition"].create(
            {
                "name": "Archive rosters other edition",
                "competition_id": other_competition.id,
                "season_id": self.season.id,
            }
        )
        division = self.env["federation.tournament"].create(
            {
                "name": "Other division",
                "edition_id": other.id,
                "competition_id": other_competition.id,
                "season_id": self.season.id,
                "date_start": fields.Date.context_today(self.env.user),
            }
        )
        self.env["federation.tournament.participant"].create(
            {"tournament_id": division.id, "team_id": self.team.id}
        )
        self.edition.write({"active": False})
        self.assertNotIn(self.roster.id, self.scope.hidden_roster_ids())
        self.assertTrue(self._visible(self.roster))


@tagged("post_install", "-at_install", "sf_app")
class TestCompetitionForceDelete(TransactionCase):
    def _competition(self, name):
        wizard = self.env["federation.practice.competition.wizard"].create(
            {
                "name": name,
                "division_count": 1,
                "teams_per_division": 4,
                "gameday_count": 1,
                "first_gameday_today": False,
                "first_gameday": fields.Date.context_today(self.env.user)
                + timedelta(days=30),
            }
        )
        wizard.action_create()
        return self.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] %s" % name)], limit=1
        )

    def test_force_delete_removes_protected_history_but_keeps_master_data(self):
        edition = self._competition("Force delete")
        division = edition.tournament_ids
        teams = (
            self.env["federation.match"]
            .search([("tournament_id", "in", division.ids)])
            .mapped("home_team_id")
        )
        publications = self.env["federation.schedule.publication"].search(
            [("schedule_id.edition_id", "=", edition.id)]
        )
        self.assertTrue(publications, "the practice competition is published")
        self.assertTrue(teams)

        wizard = (
            self.env["federation.competition.force.delete.wizard"]
            .with_context(active_model=edition._name, active_ids=edition.ids)
            .create({})
        )
        self.assertFalse(wizard.blocked)
        self.assertIn("Will be deleted", wizard.preview_html)
        with self.assertRaises(UserError):
            wizard.action_delete()
        wizard.confirmation = "DELETE"
        wizard.action_delete()

        self.assertFalse(edition.exists())
        self.assertFalse(division.exists())
        self.assertFalse(publications.exists())
        self.assertEqual(len(teams.exists()), len(teams), "teams are master data")

    def test_published_competition_must_be_unpublished_first(self):
        edition = self._competition("Force delete published")
        edition.sudo().write({"is_practice": False})
        edition.sudo().write({"website_published": True})
        with self.assertRaises(UserError):
            self.env["federation.competition.force.delete"].execute(edition)

    def test_only_system_administrators_may_force_delete(self):
        edition = self._competition("Force delete rights")
        manager = self.env["res.users"].create(
            {
                "name": "Force delete manager",
                "login": "force-delete-manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref(
                                "sports_federation_base.group_federation_manager"
                            ).id
                        ],
                    )
                ],
            }
        )
        with self.assertRaises(AccessError):
            self.env["federation.competition.force.delete"].with_user(manager).execute(
                edition
            )
