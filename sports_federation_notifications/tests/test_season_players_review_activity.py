from odoo.tests import TransactionCase, tagged

from odoo.addons.sports_federation_notifications.models.notification_dispatcher import (
    SEASON_PLAYERS_REVIEW_SUMMARY,
)


@tagged("post_install", "-at_install", "sf_season_players")
class TestSeasonPlayersReviewActivity(TransactionCase):
    """A club submission asks managers to act; handling it closes the request."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Season Players Activity Manager",
                    "login": "season.players.activity@example.com",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                cls.env.ref(
                                    "sports_federation_base.group_federation_manager"
                                ).id
                            ],
                        )
                    ],
                }
            )
        )
        cls.club = cls.env["federation.club"].create({"name": "Activity Club"})
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Activity Season",
                "date_start": "2098-01-01",
                "date_end": "2098-12-31",
                "state": "open",
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Activity",
                "last_name": "Player",
                "gender": "male",
                "birth_date": "2000-01-01",
                "club_id": cls.club.id,
            }
        )
        cls.registration = cls.env[
            "federation.club.season.registration"
        ]._get_or_create(cls.club, cls.season)

    def _review_activities(self):
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "federation.club.season.registration"),
                ("res_id", "=", self.registration.id),
                ("summary", "=like", SEASON_PLAYERS_REVIEW_SUMMARY + "%"),
            ]
        )

    def test_submission_creates_one_manager_activity(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        activities = self._review_activities()
        self.assertIn(self.manager, activities.user_id)
        self.assertEqual(
            len(activities.filtered(lambda a: a.user_id == self.manager)), 1
        )
        # Submitting the same list again does not ask twice.
        self.registration.action_submit()
        self.assertEqual(self._review_activities(), activities)

    def test_approval_closes_the_activity(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        self.assertTrue(self._review_activities())
        self.registration.action_confirm()
        self.assertFalse(self._review_activities())

    def test_cancellation_closes_the_activity(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        self.registration.action_cancel()
        self.assertFalse(self._review_activities())
