from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Run the module migration steps."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["website"]._cleanup_default_public_site_content()
