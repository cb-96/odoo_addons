from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestPhase51ScheduleHandoff(TransactionCase):
    """Regression checks for the operator-facing Schedule handoff command boundary."""

    def test_operator_actions_are_exposed_on_owning_models(self):
        schedule = self.env["federation.schedule"]
        review = self.env["federation.schedule.review"]
        publication = self.env["federation.schedule.publication"]
        self.assertTrue(hasattr(schedule, "action_open_submit_for_review"))
        self.assertTrue(hasattr(schedule, "action_submit_for_review"))
        self.assertTrue(hasattr(schedule, "action_open_current_review"))
        self.assertTrue(hasattr(review, "action_withdraw_submission"))
        self.assertTrue(hasattr(review, "action_request_changes"))
        self.assertTrue(hasattr(review, "action_approve_schedule"))
        self.assertTrue(hasattr(review, "action_publish_schedule"))
        self.assertTrue(hasattr(publication, "action_open_publication"))

    def test_review_and_publication_cannot_be_deleted(self):
        with self.assertRaises(ValidationError):
            self.env["federation.schedule.review"].unlink()
        with self.assertRaises(ValidationError):
            self.env["federation.schedule.publication"].unlink()

    def test_handoff_views_bind_buttons_to_model_actions(self):
        review_view = self.env.ref(
            "sports_federation_schedule_approval.review_form"
        ).arch_db
        schedule_view = self.env.ref(
            "sports_federation_scheduling.schedule_form"
        ).arch_db
        self.assertIn("action_open_submit_for_review", schedule_view)
        self.assertIn("action_withdraw_submission", review_view)
        self.assertIn("action_request_changes", review_view)
        self.assertIn("action_approve_schedule", review_view)
        self.assertIn("action_publish_schedule", review_view)
