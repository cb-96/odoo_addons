import importlib.util
from pathlib import Path

from odoo.tests.common import TransactionCase, tagged

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "migrations/19.0.1.5.0/end-migrate.py"
)
_spec = importlib.util.spec_from_file_location("retired_addon_cleanup", _SCRIPT)
cleanup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cleanup)

PROBE = "sports_federation_retired_probe"


@tagged("post_install", "-at_install")
class TestRetiredAddonCleanup(TransactionCase):
    def _own(self, record, name):
        self.env["ir.model.data"].create(
            {
                "module": PROBE,
                "name": name,
                "model": record._name,
                "res_id": record.id,
            }
        )

    def _dangling_menu(self, name):
        action = self.env["ir.actions.act_window"].create(
            {"name": name, "res_model": "res.partner"}
        )
        # The model of a removed addon: the action row survives, the model not.
        self.env.cr.execute(
            "UPDATE ir_act_window SET res_model = %s WHERE id = %s",
            ("federation.retired.probe", action.id),
        )
        action.invalidate_recordset()
        menu = self.env["ir.ui.menu"].create(
            {
                "name": name,
                "parent_id": self.env.ref(
                    "sports_federation_base.menu_federation_setup"
                ).id,
                "action": "ir.actions.act_window,%s" % action.id,
            }
        )
        return menu, action

    def test_purge_removes_only_records_of_the_retired_addon(self):
        self.env.cr.execute(
            "INSERT INTO ir_module_module (name, state) VALUES (%s, 'installed')",
            (PROBE,),
        )
        menu, action = self._dangling_menu("Retired Probe")
        self._own(menu, "menu_probe")
        self._own(action, "action_probe")
        # A menu another addon also declares is kept.
        shared = self.env.ref("sports_federation_people.menu_federation_player")
        self._own(shared, "menu_shared")

        self.assertTrue(cleanup.purge_retired_addon(self.env, PROBE))

        self.assertFalse(menu.exists())
        self.assertFalse(action.exists())
        self.assertTrue(shared.exists())
        self.assertFalse(
            self.env["ir.model.data"].search_count([("module", "=", PROBE)])
        )
        self.env.cr.execute(
            "SELECT state FROM ir_module_module WHERE name = %s", (PROBE,)
        )
        self.assertEqual(self.env.cr.fetchone()[0], "uninstalled")
        # Idempotent.
        cleanup.purge_retired_addon(self.env, PROBE)

    def test_unknown_addon_is_ignored(self):
        self.assertFalse(cleanup.purge_retired_addon(self.env, PROBE))

    def test_menus_on_unregistered_models_are_removed(self):
        menu, _action = self._dangling_menu("Dangling Probe")
        players = self.env.ref("sports_federation_people.menu_federation_player")
        removed = cleanup.remove_dangling_menus(self.env)
        self.assertIn(menu.id, removed)
        self.assertFalse(menu.exists())
        self.assertTrue(players.exists())
