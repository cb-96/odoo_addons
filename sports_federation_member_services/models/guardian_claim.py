import base64
import hashlib
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from .membership import manager
from .lifecycle import command, guarded, lock


class GuardianClaim(models.Model):
    _name = 'federation.guardian.claim'
    _description = 'Independent Guardian Relationship Review'
    _inherit = ['mail.thread']
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    delegate_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True)
    submitted_by_id = fields.Many2one('res.users', required=True)
    document = fields.Binary(attachment=True, required=True)
    filename = fields.Char(required=True)
    checksum = fields.Char(required=True)
    reason = fields.Text(required=True)
    valid_until = fields.Date(required=True)
    state = fields.Selection([('pending', 'Independent review'), ('verified', 'Verified relationship'), ('rejected', 'Rejected')], default='pending', required=True)
    decision_note = fields.Text()
    inspected = fields.Boolean(string='I inspected this evidence and the two identities')
    relationship_id = fields.Many2one('federation.person.relationship', readonly=True, ondelete='restrict')

    @api.model
    def _submit_claim(self, reference, reason, upload):
        if self.env.user._is_public() or not reason or not upload:
            raise ValidationError(_('Sign in and provide the reference, reason and evidence.'))
        person = self.env['res.partner'].sudo().search([('family_reference', '=', (reference or '').strip()), ('family_canonical_id', '=', False)], limit=1)
        if not person or person == self.env.user.partner_id:
            raise ValidationError(_('The relationship request could not be accepted. Ask the federation to check the reference.'))
        lock(person)
        membership = self.env['federation.person.membership'].sudo().search([
            ('person_id', '=', person.id), ('company_id', 'in', self.env.companies.ids), ('state', '=', 'active'), ('season_id.date_end', '>=', fields.Date.today())], order='id desc', limit=1)
        if not membership:
            raise ValidationError(_('The relationship request could not be accepted.'))
        existing = self.sudo().search([('person_id', '=', person.id), ('delegate_id', '=', self.env.user.partner_id.id), ('state', '=', 'pending')], limit=1)
        if existing:
            return existing.id
        policy = self.env['federation.attachment.policy']
        maximum = policy.get_policy('portal_document')['max_bytes']
        payload = upload.read(maximum + 1)
        checked = policy.validate_upload('portal_document', upload.filename, payload, mimetype=upload.content_type)
        return command(self.sudo()).create({'person_id': person.id, 'delegate_id': self.env.user.partner_id.id,
            'company_id': membership.company_id.id, 'submitted_by_id': self.env.uid, 'reason': reason,
            'document': base64.b64encode(checked['payload']), 'filename': upload.filename,
            'checksum': hashlib.sha256(checked['payload']).hexdigest(), 'valid_until': membership.season_id.date_end}).id

    @api.model_create_multi
    def create(self, vals_list):
        guarded(self.env)
        return super().create(vals_list)

    def write(self, vals):
        manager(self.env)
        if set(vals) - {'decision_note', 'inspected', 'valid_until'}:
            guarded(self.env)
        if any(claim.state != 'pending' for claim in self):
            raise ValidationError(_('Reviewed relationship evidence is immutable.'))
        return super().write(vals)

    def action_verify(self):
        manager(self.env)
        self.check_access('write')
        for claim in self.sorted('id'):
            lock(claim.person_id)
            lock(claim)
            if (claim.state != 'pending' or not claim.inspected or not claim.decision_note
                    or claim.submitted_by_id == self.env.user or claim.valid_until < fields.Date.today()
                    or claim.person_id.family_canonical_id
                    or hashlib.sha256(base64.b64decode(claim.document)).hexdigest() != claim.checksum):
                raise ValidationError(_('Independently inspect current evidence, identities, dates and decision reason.'))
            relation = self.env['federation.person.relationship'].create({
                'person_id': claim.person_id.id, 'delegate_id': claim.delegate_id.id,
                'company_id': claim.company_id.id, 'kind': 'guardian', 'valid_from': fields.Date.today(),
                'valid_until': claim.valid_until, 'reason': claim.decision_note})
            relation.action_verify()
            command(claim).write({'state': 'verified', 'relationship_id': relation.id})
        return True

    def action_reject(self):
        manager(self.env)
        self.check_access('write')
        lock(self)
        if any(claim.state != 'pending' or not claim.decision_note for claim in self):
            raise ValidationError(_('Record a rejection reason.'))
        return command(self).write({'state': 'rejected'})
