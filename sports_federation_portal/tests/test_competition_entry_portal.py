from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from odoo import fields
from odoo.exceptions import AccessError
from odoo.http import Response
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_portal.controllers import competition_portal


@tagged("post_install", "-at_install", "sf_portal_competition")
class TestCompetitionEntryPortal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Entry Portal Season",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {"name": "Entry Portal Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Entry Portal Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "registration_approval_required": True,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Entry Portal Division",
                "edition_id": cls.edition.id,
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "date_start": "2026-02-01",
                "category": "senior",
                "gender": "male",
                "max_participants": 1,
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Entry Portal Club", "code": "EPC"}
        )
        cls.other_club = cls.env["federation.club"].create(
            {"name": "Entry Portal Other Club", "code": "EPOC"}
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Entry Portal Team",
                "club_id": cls.club.id,
                "category": "senior",
                "gender": "male",
            }
        )
        cls.second_team = cls.env["federation.team"].create(
            {
                "name": "Entry Portal Second Team",
                "club_id": cls.club.id,
                "category": "senior",
                "gender": "male",
            }
        )
        cls.other_team = cls.env["federation.team"].create(
            {
                "name": "Entry Portal Other Team",
                "club_id": cls.other_club.id,
                "category": "senior",
                "gender": "male",
            }
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Entry Portal User",
                    "login": "entry.portal.user@example.com",
                    "email": "entry.portal.user@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": cls.role_type.id,
            }
        )
        now = fields.Datetime.now()
        cls.window = cls.env["federation.registration.window"].create(
            {
                "name": "Entry Portal Window",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "date_open": fields.Datetime.to_string(now - timedelta(days=1)),
                "date_close": fields.Datetime.to_string(now + timedelta(days=1)),
                "state": "open",
            }
        )

    def _controller_call(self, method_name, *args, **kwargs):
        controller = competition_portal.FederationPortalcurrent()

        def render(template, values):
            response = Response()
            response.template = template
            response.values = values
            return response

        request_stub = SimpleNamespace(
            env=self.env(user=self.user.id),
            render=render,
        )
        with patch.object(competition_portal, "request", request_stub):
            return getattr(controller, method_name)(*args, **kwargs)

    def _redirect_query(self, response):
        return parse_qs(urlparse(response.location).query)

    def test_portal_submission_uses_shared_window_validation(self):
        self.window.date_close = fields.Datetime.to_string(
            fields.Datetime.now() - timedelta(days=1)
        )

        response = self._controller_call(
            "portal_create_competition_entry",
            str(self.window.id),
            str(self.team.id),
        )

        self.assertIn("not currently open", self._redirect_query(response)["error"][0])
        self.assertFalse(
            self.env["federation.competition.entry"].search(
                [("window_id", "=", self.window.id), ("team_id", "=", self.team.id)]
            )
        )

    def test_entry_list_uses_scoped_reads_and_filters_available_windows(self):
        own_entry = self.env["federation.competition.entry"]._portal_submit_entry(
            self.division, self.team, user=self.user, window=self.window
        )
        self.env["federation.competition.entry"].sudo().create(
            {"window_id": self.window.id, "team_id": self.other_team.id}
        )
        available_window = self.env["federation.registration.window"].create(
            {
                "name": "Another Entry Portal Window",
                "edition_id": self.edition.id,
                "division_id": self.division.id,
                "date_open": self.window.date_open,
                "date_close": self.window.date_close,
                "state": "open",
            }
        )

        response = self._controller_call("portal_my_competition_entries")

        self.assertEqual(response.template, "sports_federation_portal.portal_my_competition_entries")
        self.assertEqual(response.values["entries"].ids, own_entry.ids)
        self.assertEqual(response.values["windows"].ids, available_window.ids)

    def test_portal_submission_respects_capacity_before_creation(self):
        first_entry = self.env["federation.competition.entry"]._portal_submit_entry(
            self.division, self.team, user=self.user, window=self.window
        )
        self.assertEqual(first_entry.state, "submitted")

        response = self._controller_call(
            "portal_create_competition_entry",
            str(self.window.id),
            str(self.second_team.id),
        )

        self.assertIn("capacity", self._redirect_query(response)["error"][0])
        self.assertEqual(
            self.env["federation.competition.entry"].search_count(
                [("window_id", "=", self.window.id)]
            ),
            1,
        )

    def test_withdrawn_entry_is_reused_when_representative_resubmits(self):
        entries = self.env["federation.competition.entry"]
        entry = entries._portal_submit_entry(
            self.division,
            self.team,
            notes="Initial submission",
            user=self.user,
            window=self.window,
        )
        entry.portal_withdraw(user=self.user)

        response = self._controller_call(
            "portal_create_competition_entry",
            str(self.window.id),
            str(self.team.id),
            submission_note="Resubmitted through the same entry",
        )

        self.assertIn("success", self._redirect_query(response))
        self.assertEqual(entry.state, "submitted")
        self.assertEqual(entry.submission_note, "Resubmitted through the same entry")
        self.assertEqual(
            entries.search_count(
                [("window_id", "=", self.window.id), ("team_id", "=", self.team.id)]
            ),
            1,
        )

    def test_returned_entry_can_be_corrected_and_resubmitted(self):
        entry = self.env["federation.competition.entry"]._portal_submit_entry(
            self.division,
            self.team,
            notes="Original details",
            user=self.user,
            window=self.window,
        )
        entry.action_return("Add the missing competition contact.")
        self.assertEqual(entry.get_portal_state_label(), "Returned for updates")

        entry.portal_resubmit("Corrected details", user=self.user)

        self.assertEqual(entry.state, "submitted")
        self.assertEqual(entry.submission_note, "Corrected details")
        self.assertEqual(entry.review_note, "Add the missing competition contact.")

    def test_entry_recovery_rejects_foreign_team_scope(self):
        entry = self.env["federation.competition.entry"].sudo().create(
            {"window_id": self.window.id, "team_id": self.other_team.id}
        )

        with self.assertRaises(AccessError):
            entry.portal_resubmit("Should be denied", user=self.user)

    def test_competition_entry_detail_template_is_registered(self):
        self.assertTrue(
            self.env.ref("sports_federation_portal.portal_competition_entry_detail")
        )