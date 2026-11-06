from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Preserve current legacy bytes without inferring identity, guardianship or approval.
    for document in env["federation.person.request"].search(
        [("document_revision", ">", 0)]
    ):
        document._archive_current()
