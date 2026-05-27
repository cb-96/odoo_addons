from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestCompetitionWorkspaceHttpSmoke(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace_action_id = cls.env.ref(
            "sports_federation_competition_engine.action_competition_workspace"
        ).id
        cls.workspace_menu_id = cls.env.ref(
            "sports_federation_competition_engine.menu_competition_workspace"
        ).id
        cls.admin_login = cls.env.ref("base.user_admin").login

    def test_competition_workspace_web_client_route_renders(self):
        self.authenticate(self.admin_login, "ignored")

        response = self.url_open(
            f"/web#action={self.workspace_action_id}&menu_id={self.workspace_menu_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("odoo.__session_info__", response.text)
        self.assertNotIn('name="login"', response.text)
        self.assertNotIn("Internal Server Error", response.text)