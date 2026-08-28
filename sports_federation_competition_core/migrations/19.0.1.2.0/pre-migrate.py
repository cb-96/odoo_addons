"""Remove XML records left by the retired competition-core workflow."""

from odoo import SUPERUSER_ID, api


LEGACY_XMLIDS = (
    "menu_competition_overview_v2",
    "menu_competition_roles_v2",
    "menu_competition_engine_v2_technical",
    "menu_competition_engine_v2_root",
    "action_competition_overview_v2",
    "action_competition_roles_v2",
    "competition_edition_form_v2_workflow",
)


def migrate(cr, version):
    """Delete obsolete records before current views are validated."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    removed = 0
    for name in LEGACY_XMLIDS:
        record = env.ref(
            f"sports_federation_competition_core.{name}",
            raise_if_not_found=False,
        )
        if record:
            record.unlink()
            removed += 1

    if removed:
        env.invalidate_all()
