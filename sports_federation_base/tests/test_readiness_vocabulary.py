from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReadinessVocabulary(TransactionCase):
    def setUp(self):
        super().setUp()
        self.words = self.env["federation.readiness.vocabulary"]

    def test_labels_are_the_six_shared_words(self):
        self.assertEqual(
            list(self.words.labels().values()),
            [
                "Ready",
                "Action needed",
                "Waiting for review",
                "Blocked",
                "Complete",
                "Not applicable",
            ],
        )

    def test_internal_states_map_to_shared_labels(self):
        label_for = self.words.label_for
        self.assertEqual(label_for("lineup", "submitted"), "Waiting for review")
        self.assertEqual(label_for("lineup", "approved"), "Ready")
        self.assertEqual(label_for("journey", "unknown"), "Action needed")
        self.assertEqual(label_for("compliance", "non_compliant"), "Blocked")

    def test_unknown_state_is_never_ready(self):
        self.assertEqual(
            self.words.status_for("lineup", "mystery"), vocabulary.ACTION_NEEDED
        )

    def test_badge_class_exists_for_every_status(self):
        for status in vocabulary.STATUSES:
            self.assertTrue(self.words.badge_class(status))
