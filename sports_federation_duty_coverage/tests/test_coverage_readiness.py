from odoo.tests.common import TransactionCase, tagged

from .common import CoverageFixture


@tagged("post_install", "-at_install", "sf_duty_coverage", "sf_matchday_readiness")
class TestCoverageReadiness(CoverageFixture, TransactionCase):
    def test_coverage_readiness_follows_the_detailed_state(self):
        self.env.flush_all()
        self.env.invalidate_all()
        words = self.env["federation.readiness.vocabulary"]
        match = self.match
        self.assertEqual(
            match.coverage_readiness, words.status_for("coverage", match.coverage_state)
        )
        snapshot = match._coverage_snapshot()
        self.assertEqual(snapshot["readiness"], match.coverage_readiness)
        self.assertEqual(
            snapshot["readiness_label"], words.label(match.coverage_readiness)
        )

    def test_detailed_coverage_states_stay_intact(self):
        selection = self.env["federation.match"]._fields["coverage_state"].selection
        self.assertEqual(
            [code for code, _label in selection],
            ["unchecked", "not_required", "uncovered", "needs_action", "ready"],
        )

    def test_unknown_requirements_are_never_reported_ready(self):
        words = self.env["federation.readiness.vocabulary"]
        self.assertNotEqual(words.status_for("coverage", "unchecked"), "ready")
