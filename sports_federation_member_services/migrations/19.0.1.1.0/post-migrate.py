import base64
import hashlib
from odoo import api, SUPERUSER_ID
from odoo.addons.sports_federation_member_services.models.membership import Request


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for request in env['federation.person.request'].search([]):
        values = {}
        if request.document:
            values.update(document_revision=max(1, request.document_revision),
                          document_checksum=hashlib.sha256(base64.b64decode(request.document)).hexdigest())
        if request.state == 'verified':
            request.message_post(body='Legacy verification requires revision-bound re-review. Previous reviewer: %s.' % (request.verified_by_id.display_name or 'unknown'))
            values.update(state='uploaded' if request.document else 'returned', verified_by_id=False,
                          verified_revision=0, verified_on=False)
            if not request.document:
                values['review_note'] = 'Upload replacement evidence before independent review.'
        if values:
            # Migration-only bypass of public command metadata guard.
            super(Request, request).write(values)
