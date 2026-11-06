from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError


class MemberPortal(http.Controller):
    @http.route('/my/family', type='http', auth='user', methods=['GET'], website=True)
    def family(self, **kw):
        return request.render('sports_federation_member_services.family', {
            'memberships': request.env['federation.person.membership']._portal_rows(),
            'requests': request.env['federation.person.request']._portal_rows(),
            'seasons': request.env['federation.season'].sudo().search([('state', '=', 'open')]),
            'feedback': kw.get('feedback', '')})

    @http.route('/my/family/memberships/<int:membership_id>/renew', type='http', auth='user', methods=['POST'], website=True, csrf=True)
    def renew(self, membership_id, season_id=None, **kw):
        try:
            request.env['federation.person.membership'].browse(membership_id)._renew(season_id)
        except (AccessError, ValidationError, ValueError, TypeError):
            return request.redirect('/my/family?feedback=Renewal+not+accepted')
        return request.redirect('/my/family?feedback=Renewal+requested%3B+review+is+still+required')

    @http.route('/my/family/requests/<int:request_id>/upload', type='http', auth='user', methods=['POST'], website=True, csrf=True)
    def upload(self, request_id, **kw):
        try:
            request.env['federation.person.request'].browse(request_id)._upload(request.httprequest.files.get('document'))
        except (AccessError, ValidationError):
            return request.redirect('/my/family?feedback=Upload+not+accepted')
        return request.redirect('/my/family?feedback=Uploaded%3B+not+yet+verified')
