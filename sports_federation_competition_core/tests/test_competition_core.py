from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_competition_core")
class TestCompetitionCore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {"name": "Core 26-27", "date_start": "2026-09-01", "date_end": "2027-06-30"}
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Core League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Core Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )

    def test_valid_lifecycle_records_events(self):
        self.edition.transition_competition_state("open")
        self.assertEqual(self.edition.state, "open")
        self.assertEqual(
            self.edition.event_ids[:1].event_type, "competition_state_changed"
        )

    def test_invalid_lifecycle_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.edition.transition_competition_state("closed")

    def test_role_assignment_is_unique(self):
        vals = {
            "edition_id": self.edition.id,
            "role": "schedule_planner",
            "user_id": self.env.user.id,
        }
        self.env["federation.competition.role.assignment"].create(vals)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env["federation.competition.role.assignment"].create(vals)


class TestContextualRoleGuidance(TransactionCase):
    def test_missing_role_names_required_role_and_handoff(self):
        season = self.env["federation.season"].create(
            {
                "name": "Role Guidance Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = self.env["federation.competition"].create(
            {"name": "Role Guidance", "competition_type": "league"}
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Role Guidance Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        user = self.env["res.users"].with_context(no_reset_password=True).create(
            {"name": "Unassigned Operator", "login": "unassigned.operator@example.com"}
        )
        with self.assertRaisesRegex(ValidationError, "Schedule Approver") as error:
            (
                self.env["federation.competition.role.assignment"]
                .with_user(user)
                .assert_role(edition, "schedule_approver")
            )
        self.assertIn("Competition Administrator", str(error.exception))
