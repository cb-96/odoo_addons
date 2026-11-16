import importlib.util
from pathlib import Path

from odoo.tests.common import TransactionCase, tagged

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "migrations/19.0.1.5.0/end-migrate.py"
)
_spec = importlib.util.spec_from_file_location("retired_addon_columns", _SCRIPT)
cleanup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cleanup)

PROBE = "sports_federation_retired_columns_probe"


@tagged("post_install", "-at_install")
class TestRetiredAddonColumns(TransactionCase):
    """Only columns added to remaining models are dropped one by one."""

    def _probe_field(self, model, name):
        partner_model = self.env["ir.model"]._get("res.partner")
        self.env.cr.execute(
            """
            INSERT INTO ir_model_fields
                   (name, model, model_id, field_description, ttype, state, store)
            VALUES (%s, %s, %s, '{"en_US": "Probe"}', 'char', 'base', true)
            RETURNING id
            """,
            (name, model, partner_model.id),
        )
        field_id = self.env.cr.fetchone()[0]
        self.env["ir.model.data"].create(
            {
                "module": PROBE,
                "name": "field_%s" % field_id,
                "model": "ir.model.fields",
                "res_id": field_id,
            }
        )
        return field_id

    def _has_column(self, table, column):
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = %s AND column_name = %s
            """,
            (table, column),
        )
        return bool(self.env.cr.fetchone())

    def test_column_on_remaining_model_is_dropped(self):
        self.env.cr.execute(
            "ALTER TABLE federation_season ADD COLUMN x_retired_probe varchar"
        )
        self._probe_field("federation.season", "x_retired_probe")
        self.assertEqual(cleanup._drop_fields(self.env, PROBE), 1)
        self.assertFalse(self._has_column("federation_season", "x_retired_probe"))

    def test_fields_of_unregistered_models_are_left_to_the_table_drop(self):
        # The upgrade failed on ALTER TABLE ... DROP COLUMN "id" of a retired
        # model whose id another table referenced.
        self._probe_field("federation.retired.probe", "id")
        self._probe_field("federation.retired.probe", "name")
        self.assertEqual(cleanup._drop_fields(self.env, PROBE), 0)
