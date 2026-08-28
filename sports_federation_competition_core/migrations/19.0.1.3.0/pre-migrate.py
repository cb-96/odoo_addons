"""Remove UI records left by the retired competition engine addon."""

from odoo import SUPERUSER_ID, api

UI_MODELS = (
    "ir.ui.menu",
    "ir.actions.act_window",
    "ir.actions.client",
    "ir.ui.view",
)
LEGACY_MODULE = "sports_federation_competition_engine"


def migrate(cr, version):
    """Delete stale addon UI before current division views are validated."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    removed = 0

    for model_name in UI_MODELS:
        # Re-query for each model because deleting a parent menu can cascade to
        # child menus and their ir.model.data rows in the same transaction.
        model_data = env["ir.model.data"].search(
            [("module", "=", LEGACY_MODULE), ("model", "=", model_name)]
        )
        for data in model_data:
            record = env[model_name].browse(data.res_id).exists()
            if record:
                record.unlink()
                removed += 1

    # Unlinking the target normally removes its external ID as well. Clean up
    # any orphaned metadata to make the migration safe to rerun.
    env["ir.model.data"].search(
        [("module", "=", LEGACY_MODULE), ("model", "in", UI_MODELS)]
    ).unlink()
    if removed:
        env.invalidate_all()
