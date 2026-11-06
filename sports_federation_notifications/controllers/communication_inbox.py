from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from ..models.actionable_communications import KIND_SELECTION
from ..communication_policy import delivery_label


class CommunicationInbox(http.Controller):
    def _receipt(self, receipt_id):
        receipt = request.env['federation.communication.receipt'].search([
            ('id', '=', receipt_id), ('recipient_id', '=', request.env.user.id)], limit=1)
        if not receipt:
            raise request.not_found()
        try:
            info = receipt._presentation(request.env.user)
        except AccessError:
            raise request.not_found()
        return receipt, info

    @http.route(['/my/notifications', '/my/notifications/page/<int:page>'], type='http', auth='user', website=True, methods=['GET'])
    def inbox(self, page=1, status='all', **kw):
        if page != 1:
            return request.redirect('/my/notifications')
        try:
            before = max(0, int(kw.get('before') or 0))
        except (TypeError, ValueError):
            before = 0
        status = status if status in ('acknowledged', 'unacknowledged') else 'all'
        result = request.env['federation.notification.service']._inbox_page(
            request.env.user, status=status, before=before,
        )
        return request.render('sports_federation_notifications.communication_inbox', {
            'items': result['items'], 'next_before': result['next_before'],
            'status': status, 'page_name': 'notifications',
        })

    @http.route('/my/notifications/<int:receipt_id>', type='http', auth='user', website=True, methods=['GET'])
    def detail(self, receipt_id, **kw):
        receipt, info = self._receipt(receipt_id)
        receipt.mark_seen(request.env.user)
        return request.render('sports_federation_notifications.communication_detail', {
            'receipt': receipt, 'info': info, 'deliveries': [(d, _(delivery_label(d.state))) for d in receipt.delivery_ids],
            'page_name': 'notification'})

    @http.route('/my/notifications/<int:receipt_id>/acknowledge', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def acknowledge(self, receipt_id, **kw):
        receipt, info = self._receipt(receipt_id)
        receipt._acknowledge_for(request.env.user)
        return request.redirect('/my/notifications/%s' % receipt.id)

    @http.route('/my/notifications/<int:receipt_id>/open', type='http', auth='user', website=True, methods=['GET'])
    def open_task(self, receipt_id, **kw):
        receipt, info = self._receipt(receipt_id)
        # Destination is produced by the allowlisted source adapter, never user input.
        return request.redirect(info['url'])

    @http.route('/my/notifications/preferences', type='http', auth='user', website=True, methods=['GET', 'POST'], csrf=True)
    def preferences(self, **kw):
        model = request.env['federation.communication.preference']
        saved = False
        error = False
        if request.httprequest.method == 'POST':
            try:
                model._save_for_user(request.env.user, {kind: kw.get(kind) for kind, label in KIND_SELECTION})
                saved = True
            except ValidationError as exc:
                error = str(exc)
        rows = [{'kind': kind, 'label': _(label), 'mode': model._mode_for(request.env.user, kind)} for kind, label in KIND_SELECTION]
        return request.render('sports_federation_notifications.communication_preferences', {
            'rows': rows, 'saved': saved, 'error': error, 'page_name': 'notification_preferences'})

    @http.route('/my/notifications/schedule/<int:day_id>', type='http', auth='user', website=True, methods=['GET'])
    def schedule(self, day_id, **kw):
        service = request.env['federation.notification.service']
        try:
            info = service._communication_presentation('federation.matchday', day_id, 'schedule_change', request.env.user)
        except AccessError:
            raise request.not_found()
        day = request.env['federation.matchday'].sudo().browse(day_id)
        publication = day.current_publication_id
        matches = {match.id: match for match in service._day_matches(day)}
        rows = []
        for row in publication.assignment_snapshot or []:
            match = matches.get(row.get('match_id'))
            if not match:
                continue
            court = request.env['federation.playing.area'].sudo().browse(row.get('court_id')).exists()
            rows.append({'match': match.display_name, 'court': court.display_name if court else _('Not recorded'),
                         'start': row.get('start'), 'end': row.get('end')})
        return request.render('sports_federation_notifications.communication_schedule', {
            'day': day, 'info': info, 'rows': rows, 'page_name': 'notification_schedule'})
