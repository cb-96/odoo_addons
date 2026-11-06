from odoo.exceptions import ValidationError


def post_init_hook(env):
    if env['federation.finance.event'].sudo().search_count([
            ('state', '=', 'settled'), ('event_type', '=', 'charge'), ('account_move_id', '=', False)]):
        raise ValidationError('Native accounting requires an audited migration of settled unlinked charges before activation.')
