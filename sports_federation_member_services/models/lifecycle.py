from uuid import uuid4
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import SQL
from .membership import manager
from ..lifecycle_policy import fingerprint

_COMMAND = object()


def lock(records):
    if records:
        records.flush_recordset()
        records.env.cr.execute(SQL('SELECT id FROM %s WHERE id IN %s ORDER BY id FOR UPDATE',
                                   SQL.identifier(records._table), tuple(sorted(records.ids))))
        records.invalidate_recordset()


def command(records):
    return records.with_context(member_lifecycle_token=_COMMAND)


def guarded(env):
    if env.context.get('member_lifecycle_token') is not _COMMAND:
        raise AccessError(_('Use the reviewed lifecycle command.'))


class FamilyPartner(models.Model):
    _inherit = 'res.partner'
    family_reference = fields.Char(copy=False, index=True, groups='sports_federation_base.group_federation_manager')
    family_canonical_id = fields.Many2one('res.partner', ondelete='restrict', copy=False,
                                         groups='sports_federation_base.group_federation_manager')
    _family_reference_unique = models.Constraint('unique(family_reference)', 'Family reference must be unique.')

    def action_issue_family_reference(self):
        manager(self.env)
        self.check_access('write')
        lock(self)
        for person in self:
            if person.family_canonical_id:
                raise ValidationError(_('Use the canonical identity.'))
            command(person).write({'family_reference': uuid4().hex})
        return True

    def write(self, vals):
        if {'family_reference', 'family_canonical_id'} & vals.keys():
            guarded(self.env)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get('family_reference') or v.get('family_canonical_id') for v in vals_list):
            guarded(self.env)
        return super().create(vals_list)


class FamilyRelationship(models.Model):
    _inherit = 'federation.person.relationship'

    @api.model_create_multi
    def create(self, vals_list):
        persons = self.env['res.partner'].sudo().browse([v['person_id'] for v in vals_list])
        lock(persons)
        if any(persons.mapped('family_canonical_id')):
            raise ValidationError(_('Establish access against the canonical identity after review.'))
        return super().create(vals_list)

    def action_verify(self):
        lock(self.person_id)
        return super().action_verify()

    def action_revoke(self):
        lock(self.person_id)
        return super().action_revoke()

    def write(self, vals):
        lock(self.person_id)
        return super().write(vals)


class FamilyMembership(models.Model):
    _inherit = 'federation.person.membership'
    lifecycle_revision = fields.Integer(default=0, readonly=True, copy=False)
    finance_event_id = fields.Many2one('federation.finance.event', ondelete='restrict', copy=False,
                                      groups='sports_federation_base.group_federation_manager', check_company=True)

    @api.model
    def _person_ids(self, kind='guardian'):
        ids = super()._person_ids(kind)
        return self.env['res.partner'].sudo().browse(ids).filtered(lambda p: not p.family_canonical_id).ids

    @api.model
    def _membership_person_ids(self):
        personal = self._person_ids()
        clubs = self.env['federation.club.representative'].sudo()._get_clubs_for_user(user=self.env.user)
        players = self.env['federation.player'].sudo().search([('club_id', 'in', clubs.ids), ('person_id', '!=', False), ('family_duplicate_of_id', '=', False)])
        return list(set(personal + players.person_id.ids))

    def _member_allowed(self):
        self.ensure_one()
        row = self.sudo()
        if row.person_id.id in self._person_ids():
            return True
        clubs = self.env['federation.club.representative'].sudo()._get_clubs_for_user(user=self.env.user)
        return row.club_id in clubs and bool(self.env['federation.player'].sudo().search_count([
            ('person_id', '=', row.person_id.id), ('club_id', '=', row.club_id.id), ('family_duplicate_of_id', '=', False)]))

    def _assert_person(self, person_id=None):
        self.ensure_one()
        row = self.sudo()
        if not row.exists():
            raise AccessError(_('Membership is unavailable.'))
        lock(row.person_id)
        lock(row)
        if (row.company_id not in self.env.companies or not row.with_user(self.env.user)._member_allowed()
                or (person_id is not None and row.person_id.id != int(person_id))):
            raise AccessError(_('This action does not belong to the selected family member.'))
        return row

    @api.model_create_multi
    def create(self, vals_list):
        people = self.env['res.partner'].sudo().browse([v['person_id'] for v in vals_list])
        lock(people)
        if any(people.mapped('family_canonical_id')):
            raise ValidationError(_('Use the reviewed canonical identity.'))
        if any(v.get('state', 'draft') != 'draft' for v in vals_list):
            guarded(self.env)
        return super().create(vals_list)

    def write(self, vals):
        manager(self.env)
        lock(self.person_id)
        lock(self)
        if {'state', 'lifecycle_revision'} & vals.keys():
            guarded(self.env)
        for row in self:
            super(FamilyMembership, row).write(dict(vals, lifecycle_revision=row.lifecycle_revision + 1))
        return True

    def action_activate(self):
        manager(self.env)
        self.check_access('write')
        for row in self.sorted('id'):
            lock(row.person_id)
            lock(row)
            lock(row.season_id)
            lock(row.club_id)
            if row.season_id.state != 'open':
                raise ValidationError(_('Activate membership only for an open season.'))
            if row.state != 'draft' or not row.club_id.active or row.person_id.family_canonical_id:
                raise ValidationError(_('Activate only a reviewed draft in an active club.'))
            if not row.review_note or not row.review_note.strip():
                raise ValidationError(_('Record the membership review reason before activation.'))
            required = self.env['federation.person.request'].search([
                ('membership_id', '=', row.id), ('required_for_activation', '=', True), ('state', '!=', 'cancelled')])
            if any(not doc._current_verified()
                   or (doc.valid_until and doc.valid_until < fields.Date.today()) for doc in required):
                raise ValidationError(_('Verify all required current document revisions before membership activation.'))
            command(row).write({'state': 'active'})
            row.message_post(body=_('Membership activated by federation review. Licence, payment and sporting eligibility remain separate.'))
        return True

    def _renew(self, season_id):
        self._assert_person()
        result = super()._renew(season_id)
        renewed = self.sudo().browse(result)
        if renewed.state == 'cancelled':
            raise ValidationError(_('This season already has a cancelled membership. Request reactivation instead.'))
        # Copy requirements, never evidence or approval. Replay reuses the same renewal and requirements.
        for requirement in self.env['federation.person.request'].sudo().search([
                ('membership_id', '=', self.id), ('required_for_activation', '=', True), ('state', '!=', 'cancelled')]):
            existing = self.env['federation.person.request'].sudo().search([
                ('membership_id', '=', renewed.id), ('renewed_from_id', '=', requirement.id)], limit=1)
            if not existing:
                command(self.env['federation.person.request'].sudo()).create({
                    'name': requirement.name, 'person_id': renewed.person_id.id, 'company_id': renewed.company_id.id,
                    'membership_id': renewed.id, 'required_for_activation': True, 'renewed_from_id': requirement.id,
                    'purpose': requirement.purpose, 'purpose_kind': requirement.purpose_kind, 'guardian_required': requirement.guardian_required,
                    'deadline': renewed.season_id.date_start})
        return result

    def _request_licence(self, person_id):
        row = self._assert_person(person_id)
        if row.role != 'player' or row.state != 'active':
            raise ValidationError(_('An active player membership is required to request a licence.'))
        player = self.env['federation.player'].sudo().search([('person_id', '=', row.person_id.id)], limit=1)
        if not player or player.family_duplicate_of_id or player.club_id != row.club_id:
            raise ValidationError(_('Federation staff must review the player identity and club first.'))
        lock(player)
        existing = self.env['federation.player.license'].sudo().search([
            ('player_id', '=', player.id), ('season_id', '=', row.season_id.id)], limit=1)
        if existing:
            return existing.id
        if row.season_id.date_end <= fields.Date.today():
            raise ValidationError(_('The membership season has ended.'))
        licence = self.env['federation.player.license'].sudo().create({
            'name': 'REQ-%s-%s' % (player.id, row.season_id.id), 'player_id': player.id,
            'club_id': row.club_id.id, 'season_id': row.season_id.id,
            'issue_date': max(fields.Date.today(), row.season_id.date_start),
            'expiry_date': row.season_id.date_end, 'state': 'draft'})
        return licence.id

    def _request_change(self, kind, person_id, reason, target_club_id=None):
        row = self._assert_person(person_id)
        if kind not in ('cancel', 'reactivate', 'transfer') or not reason or not reason.strip():
            raise ValidationError(_('Choose a lifecycle action and explain the request.'))
        expected = 'cancelled' if kind == 'reactivate' else 'active'
        if row.state != expected:
            raise ValidationError(_('This lifecycle action is not available for the current membership.'))
        target = self.env['federation.club'].sudo().browse(int(target_club_id or 0)).exists()
        if kind == 'transfer' and (not target or not target.active or target == row.club_id):
            raise ValidationError(_('Choose a different active destination club.'))
        model = self.env['federation.member.change'].sudo()
        existing = model.search([('membership_id', '=', row.id), ('state', '=', 'pending')], limit=1)
        if existing:
            if existing.kind != kind or existing.target_club_id != (target if kind == 'transfer' else target.browse()):
                raise ValidationError(_('Another lifecycle request is pending. Wait for federation review.'))
            return existing.id
        return command(model).create({'membership_id': row.id, 'person_id': row.person_id.id,
            'company_id': row.company_id.id, 'kind': kind, 'reason': reason.strip(),
            'target_club_id': target.id if kind == 'transfer' else False,
            'requested_by_id': self.env.uid, 'source_signature': fingerprint((row.state, row.lifecycle_revision))}).id


class MemberChange(models.Model):
    _name = 'federation.member.change'
    _description = 'Reviewed Membership Lifecycle Request'
    _inherit = ['mail.thread']
    membership_id = fields.Many2one('federation.person.membership', required=True, ondelete='restrict')
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True)
    kind = fields.Selection([('cancel', 'Cancellation'), ('reactivate', 'Reactivation'), ('transfer', 'Membership transfer')], required=True)
    target_club_id = fields.Many2one('federation.club', ondelete='restrict')
    reason = fields.Text(required=True)
    requested_by_id = fields.Many2one('res.users', required=True)
    source_signature = fields.Char(required=True)
    state = fields.Selection([('pending', 'Federation review'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', required=True)
    decision_note = fields.Text()
    decided_by_id = fields.Many2one('res.users', readonly=True)
    result_membership_id = fields.Many2one('federation.person.membership', readonly=True, ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        guarded(self.env)
        return super().create(vals_list)

    def write(self, vals):
        manager(self.env)
        if set(vals) - {'decision_note'}:
            guarded(self.env)
        if any(row.state != 'pending' for row in self):
            raise ValidationError(_('Decided requests are immutable.'))
        return super().write(vals)

    def action_approve(self):
        manager(self.env)
        self.check_access('write')
        for change in self.sorted('id'):
            row = change.membership_id
            lock(row.person_id)
            lock(row)
            lock(change)
            if change.state != 'pending' or not change.decision_note:
                raise ValidationError(_('Review a pending request and record a decision reason.'))
            if fingerprint((row.state, row.lifecycle_revision)) != change.source_signature:
                raise ValidationError(_('Membership changed since this request. Reject and request a fresh review.'))
            result = row
            if change.kind == 'cancel':
                command(row).write({'state': 'cancelled'})
            elif change.kind == 'reactivate':
                command(row).write({'state': 'draft'})
            else:
                if not change.target_club_id.active:
                    raise ValidationError(_('Destination club is inactive.'))
                result = self.env['federation.person.membership'].search([
                    ('person_id', '=', row.person_id.id), ('season_id', '=', row.season_id.id),
                    ('club_id', '=', change.target_club_id.id), ('role', '=', row.role)], limit=1)
                if result:
                    raise ValidationError(_('Destination membership already exists. Resolve it explicitly before transfer.'))
                result = self.env['federation.person.membership'].create({
                    'person_id': row.person_id.id, 'company_id': row.company_id.id, 'club_id': change.target_club_id.id,
                    'season_id': row.season_id.id, 'role': row.role})
                command(row).write({'state': 'cancelled'})
            command(change).write({'state': 'approved', 'decided_by_id': self.env.uid, 'result_membership_id': result.id})
            row.message_post(body=_('Membership lifecycle decision recorded. Player club, licences, invoices and roster eligibility were not changed.'))
        return True

    def action_reject(self):
        manager(self.env)
        self.check_access('write')
        lock(self)
        if any(row.state != 'pending' or not row.decision_note for row in self):
            raise ValidationError(_('Record a reason for each pending rejection.'))
        return command(self).write({'state': 'rejected', 'decided_by_id': self.env.uid})


class FamilyDocument(models.Model):
    _inherit = 'federation.person.request'
    membership_id = fields.Many2one('federation.person.membership', ondelete='restrict', index=True)
    required_for_activation = fields.Boolean(default=False)
    purpose_kind = fields.Selection([('generic', 'Membership evidence'), ('parental', 'Player parental approval')], default='generic', required=True)
    evidence_revision_ids = fields.One2many('federation.member.evidence.revision', 'request_id', readonly=True)
    parental_approval_id = fields.Many2one('federation.player.parental.approval', ondelete='restrict', readonly=True, copy=False)
    renewed_from_id = fields.Many2one('federation.person.request', ondelete='restrict', copy=False)
    _renewed_requirement_unique = models.Constraint('unique(membership_id,renewed_from_id)', 'A renewal requirement is copied once.')

    @api.model_create_multi
    def create(self, vals_list):
        lock(self.env['res.partner'].sudo().browse([v['person_id'] for v in vals_list]))
        return super().create(vals_list)

    def write(self, vals):
        if 'parental_approval_id' in vals:
            guarded(self.env)
        if any(row.state in ('uploaded', 'verified') for row in self) and {'membership_id', 'required_for_activation', 'purpose_kind'} & vals.keys():
            raise ValidationError(_('Reviewed requirement scope cannot change.'))
        lock(self.person_id)
        return super().write(vals)

    @api.constrains('membership_id', 'person_id', 'company_id')
    def _check_membership_scope(self):
        for row in self.filtered('membership_id'):
            if row.person_id != row.membership_id.person_id or row.company_id != row.membership_id.company_id:
                raise ValidationError(_('Document requirement and membership must refer to the same person and company.'))

    def _current_verified(self):
        self.ensure_one()
        if self.purpose_kind != 'parental':
            import base64, hashlib
            return self.state == 'verified' and self.verified_revision == self.document_revision and hashlib.sha256(base64.b64decode(self.document or b'')).hexdigest() == self.document_checksum
        import base64, hashlib
        approval = self.parental_approval_id
        return bool(approval and approval.player_id.person_id == self.person_id and not approval.player_id.family_duplicate_of_id and approval.state == 'verified' and
                    hashlib.sha256(base64.b64decode(approval.approval_document or b'')).hexdigest() == self.document_checksum and
                    (not approval.valid_until or approval.valid_until >= fields.Date.today()))

    def _upload(self, upload):
        with self.env.cr.savepoint():
            return self._upload_current(upload)

    def _upload_current(self, upload):
        lock(self.sudo().person_id)
        if not self._allowed():
            raise AccessError(_('Document access changed.'))
        self.sudo()._archive_current()
        result = super()._upload(upload)
        row = self.sudo()
        row._archive_current()
        if row.purpose_kind == 'parental':
            if not row.guardian_required:
                raise ValidationError(_('Parental approval requests must require a verified guardian.'))
            player = self.env['federation.player'].sudo().search([('person_id', '=', row.person_id.id)], limit=1)
            if not player or player.family_duplicate_of_id:
                raise ValidationError(_('Review the canonical player identity before uploading parental approval.'))
            values = {'player_id': player.id, 'guardian_name': self.env.user.partner_id.name,
                'approval_date': fields.Date.today(), 'valid_until': row.valid_until,
                'approval_document': row.document, 'approval_document_filename': row.filename,
                'submitted_by_id': self.env.uid}
            approval = self.env['federation.player.parental.approval'].sudo().create(values)
            from .membership import Request
            super(Request, row).write({'parental_approval_id': approval.id})
        return result

    def action_verify(self):
        if self.purpose_kind == 'parental':
            manager(self.env)
            self.check_access('read')
            if not self.parental_approval_id:
                raise ValidationError(_('Upload current evidence first.'))
            return {'type': 'ir.actions.act_window', 'res_model': 'federation.player.parental.approval',
                    'res_id': self.parental_approval_id.id, 'view_mode': 'form', 'target': 'current'}
        return super().action_verify()

    def _verify_revision(self, revision, checksum):
        if self.purpose_kind == 'parental':
            raise ValidationError(_('Verify parental evidence through the owning parental-approval workflow.'))
        return super()._verify_revision(revision, checksum)

    def _archive_current(self):
        self.ensure_one()
        if not self.document or not self.document_revision:
            return
        archive = self.env['federation.member.evidence.revision'].sudo()
        if not archive.search_count([('request_id', '=', self.id), ('revision', '=', self.document_revision)]):
            command(archive).create({'request_id': self.id, 'company_id': self.company_id.id,
                'person_id': self.person_id.id, 'revision': self.document_revision, 'checksum': self.document_checksum,
                'document': self.document, 'filename': self.filename, 'uploaded_by_id': self.uploaded_by_id.id})

    def _review_lock(self):
        lock(self.person_id)
        return super()._review_lock()


class EvidenceRevision(models.Model):
    _name = 'federation.member.evidence.revision'
    _description = 'Immutable Member Evidence Revision'
    request_id = fields.Many2one('federation.person.request', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True)
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    revision = fields.Integer(required=True)
    checksum = fields.Char(required=True)
    document = fields.Binary(attachment=True, required=True)
    filename = fields.Char()
    uploaded_by_id = fields.Many2one('res.users', required=True)
    _revision_unique = models.Constraint('unique(request_id,revision)', 'This evidence revision is already retained.')

    @api.model_create_multi
    def create(self, vals_list):
        guarded(self.env)
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_('Evidence revisions are immutable.'))

    def unlink(self):
        raise AccessError(_('Evidence history requires the governed retention process.'))
