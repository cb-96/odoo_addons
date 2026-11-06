from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

CHECKIN_FIELDS = {'checkin_requested_on', 'checkin_requested_by_id', 'checkin_signature'}


class MobileOfficial(models.Model):
    _inherit = 'federation.match.referee'
    checkin_requested_on = fields.Datetime(readonly=True, copy=False)
    checkin_requested_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    checkin_signature = fields.Char(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if any(CHECKIN_FIELDS & vals.keys() for vals in vals_list):
            raise AccessError(_('Check-in evidence is command-owned.'))
        return super().create(vals_list)

    def write(self, vals):
        if CHECKIN_FIELDS & vals.keys():
            raise AccessError(_('Use the authenticated check-in request command.'))
        return super().write(vals)

    def _request_mobile_checkin(self, user, signature):
        self.ensure_one()
        if user != self.env.user or self.referee_id.user_id != user:
            raise AccessError(_('Only the assigned official may request check-in.'))
        self._portal_assert_access(user=user)
        self._coverage_lock()
        if not signature or signature != self._coverage_signature():
            raise ValidationError(_('Schedule changed. Review and accept the current assignment first.'))
        if not self._coverage_current() or not self.coverage_accepted or not self.coverage_eligible:
            raise ValidationError(_('Current acceptance and eligibility are required before requesting check-in.'))
        if self.checkin_signature != signature:
            # Scoped elevation records a request only; manager-confirmed attendance remains separate.
            super(MobileOfficial, self.sudo()).write({
                'checkin_requested_on': fields.Datetime.now(), 'checkin_requested_by_id': user.id,
                'checkin_signature': signature})
        return True
