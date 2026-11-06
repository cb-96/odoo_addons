from odoo import api, SUPERUSER_ID
from odoo.addons.sports_federation_accounting.hooks import post_init_hook


def migrate(cr, version):
    post_init_hook(api.Environment(cr, SUPERUSER_ID, {}))
    cr.execute(
        "UPDATE federation_finance_event SET invoice_ref=account_move_id::text WHERE account_move_id IS NOT NULL"
    )
