from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_season_players")
class TestSeasonPlayersReviewTask(TransactionCase):
    """Submitted club player lists are federation work in the Review Queue."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Season Players Reviewer",
                    "login": "season.players.reviewer@example.com",
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
        cls.club = cls.env["federation.club"].create({"name": "Review Task Club"})
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Review Task Season",
                "date_start": "2098-01-01",
                "date_end": "2098-12-31",
                "state": "open",
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Review",
                "last_name": "Task",
                "gender": "female",
                "birth_date": "2000-01-01",
                "club_id": cls.club.id,
            }
        )
        cls.registration = cls.env[
            "federation.club.season.registration"
        ]._get_or_create(cls.club, cls.season)
        cls.Task = cls.env["federation.operation.task"]

    def _review_tasks(self):
        return self.Task.sudo().search(
            [
                ("task_type", "=", "season_players_review"),
                ("source_model", "=", "federation.club.season.registration"),
                ("source_record_id", "=", self.registration.id),
            ]
        )

    def test_draft_list_is_not_federation_work(self):
        self.registration._add_players(self.player)
        self.Task.sync_for_user(user=self.manager)
        self.assertFalse(self._review_tasks())

    def test_submitted_list_is_queued_until_approved(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        self.Task.sync_for_user(user=self.manager)
        task = self._review_tasks()
        self.assertEqual(len(task), 1)
        self.assertEqual(task.audience, "manager")
        self.assertEqual(task.state, "open")
        self.assertEqual(task.responsible_club_id, self.club)
        self.assertEqual(task.season_id, self.season)
        action = task.action_open_source()
        self.assertEqual(action["res_model"], "federation.club.season.registration")
        self.assertEqual(action["res_id"], self.registration.id)

        self.registration.action_confirm()
        self.Task.sync_for_user(user=self.manager)
        self.assertEqual(task.state, "done")

    def test_top_up_reopens_the_same_task(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        self.registration.action_confirm()
        self.Task.sync_for_user(user=self.manager)
        second = self.player.copy({"first_name": "Second"})
        self.registration._add_players(second)
        self.registration.action_submit()
        self.Task.sync_for_user(user=self.manager)
        task = self._review_tasks()
        self.assertEqual(len(task), 1)
        self.assertEqual(task.state, "open")

    def test_closed_season_is_not_queued(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        self.season.state = "closed"
        self.Task.sync_for_user(user=self.manager)
        self.assertFalse(self._review_tasks())

    def test_review_queue_lists_the_submitted_list(self):
        self.registration._add_players(self.player)
        self.registration.action_submit()
        # Opening the queue refreshes the projection for the manager.
        self.Task.with_user(self.manager).action_open_review_queue()
        tasks = self.Task.with_user(self.manager).search(
            [("audience", "=", "manager"), ("state", "!=", "done")]
        )
        self.assertTrue(self._review_tasks())
        self.assertIn(self._review_tasks(), tasks)
