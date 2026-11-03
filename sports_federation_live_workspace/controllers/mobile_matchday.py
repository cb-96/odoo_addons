from urllib.parse import urlencode
from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.addons.sports_federation_duty_coverage.controllers.workspace import Workspace


class MobileMatchday(Workspace):
    def _manager_assignment(self, assignment_id):
        if not request.env.user.has_group('sports_federation_base.group_federation_manager'):
            raise request.not_found()
        assignment = request.env['federation.match.referee'].browse(assignment_id).exists()
        if not assignment:
            raise request.not_found()
        try:
            assignment.check_access('write')
            assignment.match_id._coverage_assert_manager()
        except AccessError:
            raise request.not_found()
        return assignment

    @http.route('/my/matchday-mobile', type='http', auth='user', website=True, methods=['GET'])
    def mobile_home(self, **kw):
        manager = request.env.user.has_group('sports_federation_base.group_federation_manager')
        courts = request.env['federation.court.commands'].courts() if not request.env.user.share else []
        assignments = request.env['federation.match.referee'].sudo().search([
            ('referee_id.user_id', '=', request.env.user.id), ('fixture_id', '!=', False),
            ('publication_id.state', '=', 'live'), ('state', 'in', ['draft', 'confirmed'])], order='id', limit=50)
        assignments = assignments.filtered(lambda assignment: assignment._coverage_current())
        manager_rows = []
        if manager:
            matches = request.env['federation.match'].search([
                ('schedule_publication_id.state', '=', 'live'), ('state', '!=', 'cancelled')], order='date_scheduled,id', limit=50)
            for match in matches:
                if match.schedule_publication_id != match.schedule_publication_id.matchday_id.current_publication_id:
                    continue
                manager_rows.append({'match': match, 'assignments': match.referee_assignment_ids.filtered(
                    lambda assignment: assignment.publication_id == match.schedule_publication_id),
                    'coverage': match._coverage_snapshot()})
        return request.render('sports_federation_live_workspace.mobile_home', {
            'courts': courts, 'assignments': assignments, 'manager_rows': manager_rows,
            'manager': manager, 'success': kw.get('success'), 'error': kw.get('error'), 'page_name': 'mobile_matchday'})

    @http.route()
    def detail(self, assignment_id, filterby='current', **kw):
        response = super().detail(assignment_id, filterby=filterby, **kw)
        if getattr(response, 'qcontext', None):
            assignment = response.qcontext.get('assignment')
            if assignment:
                response.qcontext['checkin_current'] = bool(assignment.checkin_requested_on and assignment.checkin_signature == assignment._coverage_signature())
        return response

    @http.route('/my/duty-assignments/<int:assignment_id>/checkin', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def checkin(self, assignment_id, signature=None, **kw):
        assignment = self._owned(assignment_id)
        try:
            with request.env.cr.savepoint():
                assignment._request_mobile_checkin(request.env.user, signature)
            query = {'success': _('Check-in requested. The organiser still confirms attendance separately.')}
        except (AccessError, ValidationError) as error:
            query = {'error': str(error)}
        return request.redirect('/my/duty-assignments/%s?%s' % (assignment_id, urlencode(query)), code=303)

    @http.route('/my/matchday-mobile/assignments/<int:assignment_id>/present', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def confirm_presence(self, assignment_id, signature=None, **kw):
        assignment = self._manager_assignment(assignment_id)
        try:
            with request.env.cr.savepoint():
                assignment._coverage_lock()
                if not signature or signature != assignment._coverage_signature():
                    raise ValidationError(_('Coverage changed. Reload before confirming attendance.'))
                assignment.action_mark_present()
            query = {'success': _('Attendance confirmed by organiser. This is separate from assignment acceptance.')}
        except (AccessError, ValidationError) as error:
            query = {'error': str(error)}
        return request.redirect('/my/matchday-mobile?%s' % urlencode(query), code=303)

    @http.route('/my/matchday-mobile/assignments/<int:assignment_id>/replace', type='http', auth='user', website=True, methods=['GET', 'POST'], csrf=True)
    def replace(self, assignment_id, wizard_id=None, referee_id=None, reason=None, **kw):
        assignment = self._manager_assignment(assignment_id)
        wizard_model = request.env['federation.coverage.resolve.wizard']
        error = False
        wizard = wizard_model.browse()
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    wizard = wizard_model.browse(int(wizard_id or 0)).exists()
                    if not wizard or wizard.create_uid != request.env.user or wizard.assignment_id != assignment or wizard.operation != 'replace':
                        raise AccessError(_('Replacement preview is not yours or no longer exists.'))
                    if wizard.applied and (wizard.referee_id.id != int(referee_id or 0) or wizard.reason.strip() != (reason or '').strip()):
                        raise ValidationError(_('This preview was already applied with different replacement details.'))
                    if not wizard.applied:
                        wizard.write({'referee_id': int(referee_id or 0), 'reason': (reason or '').strip()})
                    wizard.action_apply()
                return request.redirect('/my/matchday-mobile?' + urlencode({'success': _('Replacement recorded. The successor must accept before attendance can be confirmed.')}), code=303)
            except (AccessError, ValidationError, ValueError) as exc:
                error = str(exc)
        # Reopen an explicit current preview after a stale/failed submission.
        assignment.match_id._coverage_assert_current()
        wizard = wizard_model.create({'match_id': assignment.match_id.id, 'assignment_id': assignment.id,
                                      'operation': 'replace', 'selected_role': assignment.role})
        wizard.write({'expected_signature': wizard._signature()})
        referees = request.env['federation.referee'].search([('active', '=', True)], order='name')
        return request.render('sports_federation_live_workspace.mobile_replacement', {
            'assignment': assignment, 'wizard': wizard, 'referees': referees, 'error': error,
            'page_name': 'mobile_replacement'})
