from datetime import timedelta
from markupsafe import Markup, escape
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from ..communication_policy import identity, retry_delay

KIND_SELECTION = [
    ('schedule_change', 'Published schedule or venue changes'),
    ('official_response', 'Official assignments and coverage'),
    ('document_returned', 'Document corrections'),
    ('due_soon', 'Due-soon work'),
    ('delivery_failure', 'Delivery recovery'),
]


def _lock(env, key):
    # Serialise the exact logical notification across overlapping roles and workers.
    number = int(identity(key, 0)[:15], 16)
    env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [number])


class CommunicationPreference(models.Model):
    _name = 'federation.communication.preference'
    _description = 'Participant Communication Preference'
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    kind = fields.Selection(KIND_SELECTION, required=True)
    mode = fields.Selection([('immediate', 'Email promptly'), ('digest', 'Daily digest'),
                             ('inbox', 'Inbox only')], required=True, default='immediate')
    _user_kind_unique = models.Constraint('unique(user_id,kind)', 'One preference per category and user.')

    @api.model
    def _mode_for(self, user, kind):
        preference = self.sudo().search([('user_id', '=', user.id), ('kind', '=', kind)], limit=1)
        return preference.mode or ('digest' if kind == 'due_soon' else 'inbox' if kind == 'delivery_failure' else 'immediate')

    @api.model
    def _save_for_user(self, user, values):
        if user != self.env.user:
            raise AccessError(_('You can only change your own communication preferences.'))
        for kind, mode in values.items():
            if kind not in dict(KIND_SELECTION) or mode not in ('immediate', 'digest', 'inbox'):
                raise ValidationError(_('Invalid communication preference.'))
        for kind, mode in values.items():
            _lock(self.env, 'preference:%s:%s' % (user.id, kind))
            existing = self.sudo().search([('user_id', '=', user.id), ('kind', '=', kind)], limit=1)
            if existing:
                existing.write({'mode': mode})
            else:
                self.sudo().create({'user_id': user.id, 'kind': kind, 'mode': mode})
            if mode == 'immediate':
                receipts = self.env['federation.communication.receipt'].sudo().search([('recipient_id', '=', user.id), ('kind', '=', kind), ('delivery_ids', '=', False), ('superseded_on', '=', False)])
                for receipt in receipts:
                    try:
                        info = receipt._presentation(user)
                    except AccessError:
                        continue
                    if info.get('complete'):
                        continue
                    key = identity(receipt.event_key, user.id)
                    _lock(self.env, key)
                    delivery = self.env['federation.communication.delivery'].sudo()
                    if not delivery.search_count([('delivery_key', '=', key)]):
                        delivery.create({'name': _('Federation notification'), 'delivery_key': key, 'recipient_id': user.id, 'receipt_ids': [(6, 0, receipt.ids)]})
        return True


class CommunicationReceipt(models.Model):
    _name = 'federation.communication.receipt'
    _description = 'Participant Notification Inbox Item'
    _order = 'available_on desc,id desc'
    name = fields.Char(required=True)
    event_key = fields.Char(required=True, index=True)
    recipient_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    kind = fields.Selection(KIND_SELECTION, required=True, index=True)
    target_model = fields.Char(required=True)
    target_res_id = fields.Integer(required=True)
    roles = fields.Char()
    urgent = fields.Boolean(default=False)
    occurred_on = fields.Datetime(required=True)
    available_on = fields.Datetime(required=True, default=fields.Datetime.now)
    acknowledged_on = fields.Datetime(readonly=True)
    acknowledged_by_id = fields.Many2one('res.users', readonly=True)
    superseded_on = fields.Datetime(readonly=True)
    delivery_ids = fields.Many2many('federation.communication.delivery', 'federation_communication_delivery_receipt_rel',
                                   'receipt_id', 'delivery_id', readonly=True)
    _event_recipient_unique = models.Constraint('unique(event_key,recipient_id)', 'One inbox item per event and recipient.')

    def _presentation(self, user):
        self.ensure_one()
        if self.recipient_id != user:
            raise AccessError(_('This notification belongs to another recipient.'))
        return self.env['federation.notification.service']._communication_presentation(
            self.target_model, self.target_res_id, self.kind, user)

    def _acknowledge_for(self, user):
        self.ensure_one()
        self._presentation(user)
        _lock(self.env, 'acknowledge:%s' % self.id)
        self.invalidate_recordset(['acknowledged_on'])
        if not self.acknowledged_on:
            self.sudo().write({'acknowledged_on': fields.Datetime.now(), 'acknowledged_by_id': user.id})
        return True


class CommunicationDelivery(models.Model):
    _name = 'federation.communication.delivery'
    _description = 'Recoverable Participant Notification Delivery'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc,id desc'
    name = fields.Char(required=True)
    delivery_key = fields.Char(required=True, index=True)
    recipient_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    receipt_ids = fields.Many2many('federation.communication.receipt', 'federation_communication_delivery_receipt_rel',
                                 'delivery_id', 'receipt_id')
    mail_id = fields.Many2one('mail.mail', ondelete='set null', readonly=True)
    log_id = fields.Many2one('federation.notification.log', ondelete='set null', readonly=True)
    state = fields.Selection([('pending', 'Waiting to queue'), ('queued', 'Queued for email'),
                              ('sent', 'Accepted by outbound mail server'), ('failed', 'Delivery failed'),
                              ('cancelled', 'Cancelled'), ('suppressed', 'Inbox only')], default='pending', required=True, index=True)
    attempts = fields.Integer(default=0, readonly=True)
    next_attempt_on = fields.Datetime(index=True)
    accepted_on = fields.Datetime(readonly=True)
    last_checked_on = fields.Datetime(index=True)
    escalated_on = fields.Datetime(readonly=True)
    failure_note = fields.Text(readonly=True)
    _delivery_key_unique = models.Constraint('unique(delivery_key)', 'Delivery retries reuse the same logical delivery.')

    def action_retry_delivery(self):
        if not self.env.user.has_group('sports_federation_base.group_federation_manager'):
            raise AccessError(_('Only a federation manager can recover outbound delivery.'))
        for delivery in self:
            if delivery.state != 'failed':
                raise ValidationError(_('Only failed delivery can be retried.'))
            delivery.sudo()._queue_email(retry=True)
        return True

    def _queue_email(self, retry=False):
        self.ensure_one()
        _lock(self.env, 'delivery:%s' % self.id)
        self.invalidate_recordset()
        if not self.mail_id and self.attempts > 0:
            raise ValidationError(_('Previously queued mail is missing. Verify whether it was sent before recreating delivery.'))
        if self.state in ('sent', 'cancelled', 'suppressed') or (self.state == 'queued' and not retry):
            return
        user = self.recipient_id
        valid = self.env['federation.communication.receipt'].browse()
        for receipt in self.receipt_ids:
            try:
                info = receipt._presentation(user)
                if info.get('complete') or (receipt.kind == 'due_soon' and receipt.acknowledged_on):
                    continue
                mode = self.env['federation.communication.preference']._mode_for(user, receipt.kind)
                if mode == 'digest' and not self.delivery_key.startswith('digest:'):
                    self.write({'receipt_ids': [(3, receipt.id)]})
                    continue
                if mode != 'inbox':
                    valid |= receipt
            except AccessError:
                continue
        if not user.active or not valid:
            self.write({'state': 'cancelled', 'failure_note': _('Recipient no longer authorised or email disabled.')})
            if self.mail_id and self.mail_id.state in ('outgoing', 'exception'):
                self.mail_id.write({'state': 'cancel'})
            return
        if not user.partner_id.email:
            self._fail(_('Recipient has no email address. Update the contact, then retry delivery.'))
            return
        # Generic email avoids copying document notes or private source data outside the inbox.
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        links = Markup('').join(Markup('<li><a href="%s/my/notifications/%s">%s</a></li>') %
                               (escape(base), receipt.id, escape(receipt.name)) for receipt in valid)
        body = Markup('<p>You have federation work to review.</p><ul>%s</ul><p>Delivery and acknowledgement do not complete the underlying task.</p>') % links
        if self.mail_id:
            if self.mail_id.state == 'sent':
                self._accepted()
                return
            if self.mail_id.state == 'outgoing':
                self.write({'state': 'queued'})
                return
            self.mail_id.write({'state': 'outgoing', 'email_to': user.partner_id.email,
                                'recipient_ids': [(5, 0, 0)], 'body_html': body})
        else:
            mail = self.env['mail.mail'].sudo().create({
                'subject': self.name, 'body_html': body, 'email_to': user.partner_id.email,
                'email_from': self.env.company.partner_id.email_formatted or user.partner_id.email_formatted,
                'auto_delete': False,
            })
            self.write({'mail_id': mail.id})
        if not self.log_id:
            log = self.env['federation.notification.log'].sudo().create({
                'name': self.name, 'target_model': self._name, 'target_res_id': self.id,
                'notification_type': 'email', 'recipient_partner_id': user.partner_id.id,
                'recipient_email': user.partner_id.email, 'state': 'pending',
                'correlation_id': self.delivery_key,
            })
            self.write({'log_id': log.id})
        self.write({'state': 'queued', 'attempts': self.attempts + 1, 'failure_note': False,
                    'next_attempt_on': False})
        self.log_id.write({'state': 'pending', 'attempt_count': self.attempts,
                           'last_attempt_on': fields.Datetime.now(), 'operator_message': False})

    def _accepted(self):
        if self.state == 'sent':
            return
        self.write({'state': 'sent', 'accepted_on': fields.Datetime.now(), 'failure_note': False})
        if self.log_id:
            self.log_id.write({'state': 'sent', 'sent_on': fields.Datetime.now(), 'operator_message': False})

    def _fail(self, note):
        self.write({'state': 'failed', 'failure_note': note,
                    'next_attempt_on': fields.Datetime.now() + timedelta(minutes=retry_delay(self.attempts))})
        if self.log_id:
            self.log_id.write({'state': 'failed', 'operator_message': note})

    def _escalate(self):
        self.ensure_one()
        if self.escalated_on:
            return
        managers = self.env.ref('sports_federation_base.group_federation_manager').sudo().user_ids.filtered('active')
        for manager in managers:
            self.activity_schedule('mail.mail_activity_data_todo', user_id=manager.id,
                                   summary=_('Recover failed participant notification'),
                                   note=_('Retry this delivery after correcting the contact or mail configuration. Do not repeat the business action.'))
        self.write({'escalated_on': fields.Datetime.now()})
        self.env['federation.notification.service']._publish_action(
            self, 'delivery_failure', 'delivery-failure:%s' % self.id,
            [(manager.id, 'manager') for manager in managers])

    @api.model
    def _cron_dispatch(self):
        for delivery in self.sudo().search([('state', 'in', ['pending', 'queued', 'failed'])], order='last_checked_on asc,id', limit=500):
            _lock(self.env, 'delivery:%s' % delivery.id)
            delivery.invalidate_recordset()
            delivery.write({'last_checked_on': fields.Datetime.now()})
            if delivery.state == 'queued':
                if delivery.mail_id.state == 'sent':
                    delivery._accepted()
                elif delivery.mail_id.state == 'exception':
                    delivery._fail(_('Outbound mail failed. Inspect the mail server error in the backend.'))
                elif not delivery.mail_id:
                    delivery._fail(_('The queued mail record is missing. Investigate before retrying.'))
            if delivery.state == 'pending':
                delivery._queue_email()
            elif delivery.state == 'failed':
                if delivery.attempts >= 3 or not delivery.recipient_id.partner_id.email or (delivery.attempts > 0 and not delivery.mail_id):
                    delivery._escalate()
                elif delivery.next_attempt_on and delivery.next_attempt_on <= fields.Datetime.now():
                    delivery._queue_email(retry=True)
        return True
