"""Page views share the task projection instead of each rebuilding it."""

from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.sports_federation_portal.models import task_projection


@tagged("post_install", "-at_install", "sf_task_projection")
class TestTaskProjectionFreshness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env["federation.operation.task"]
        cls.user = cls.env.ref("base.user_admin")
        cls.env["ir.config_parameter"].sudo().set_param(
            "sports_federation_portal.task_projection_max_age", "30"
        )

    def setUp(self):
        super().setUp()
        task_projection._LAST_SYNC.clear()
        self.addCleanup(task_projection._LAST_SYNC.clear)

    def _request(self, method="GET"):
        return SimpleNamespace(httprequest=SimpleNamespace(method=method))

    def _sync(self, request):
        """Run sync_for_user as if inside ``request``; return rebuild count."""
        Projection = type(self.env["federation.task.projection"])
        with patch.object(
            task_projection, "_current_http_request", return_value=request
        ), patch.object(
            Projection, "synchronize", autospec=True, return_value=self.Task
        ) as rebuild:
            self.Task.sync_for_user(user=self.user)
        return rebuild.call_count

    def test_outside_requests_every_call_rebuilds(self):
        self.assertEqual(self._sync(None), 1)
        self.assertEqual(self._sync(None), 1)

    def test_one_rebuild_per_request(self):
        request = self._request("POST")
        self.assertEqual(self._sync(request), 1)
        self.assertEqual(self._sync(request), 0)

    def test_recent_projection_is_reused_by_the_next_page_view(self):
        self.assertEqual(self._sync(self._request()), 1)
        self.assertEqual(self._sync(self._request()), 0)

    def test_posts_always_rebuild(self):
        self.assertEqual(self._sync(self._request()), 1)
        self.assertEqual(self._sync(self._request("POST")), 1)

    def test_an_old_projection_is_rebuilt(self):
        self.assertEqual(self._sync(self._request()), 1)
        key = (self.env.cr.dbname, self.user.id)
        task_projection._LAST_SYNC[key] -= 31
        self.assertEqual(self._sync(self._request()), 1)

    def test_zero_max_age_disables_reuse(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation_portal.task_projection_max_age", "0"
        )
        self.assertEqual(self._sync(self._request()), 1)
        self.assertEqual(self._sync(self._request()), 1)

    def test_a_portal_change_discards_the_recent_projection(self):
        self.assertEqual(self._sync(self._request()), 1)
        self.env["federation.portal.privilege"]._log_portal_audit(
            event_type="portal_write",
            description="test",
            records=self.env["res.partner"].browse(),
            user=self.user,
        )
        self.assertEqual(self._sync(self._request()), 1)

    def test_busy_clubs_show_current_tasks_without_writing(self):
        with patch.object(
            task_projection._ProjectionFreshness, "try_lock", return_value=False
        ):
            self.assertEqual(self._sync(None), 0)

    def test_lock_is_free_in_a_single_transaction(self):
        freshness = task_projection._ProjectionFreshness(self.env, self.user)
        self.assertTrue(freshness.try_lock())
        # Transaction-level locks are re-entrant within the same transaction.
        self.assertTrue(freshness.try_lock())
