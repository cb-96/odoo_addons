import base64
import hashlib
from psycopg2 import IntegrityError
from psycopg2.errors import SerializationFailure
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


def manager(env):
    if not env.user.has_group('sports_federation_base.group_federation_manager'):
        raise AccessError(_('Membership administration permission is required.'))


class Player(models.Model):
    _inherit = 'federation.player'
    person_id = fields.Many2one('res.partner', ondelete='restrict', index=True,
                               groups='sports_federation_base.group_federation_manager')
    _person_unique = models.Constraint('UNIQUE(person_id)', 'A person can have only one player identity.')

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get('person_id') for v in vals_list):
            manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        if 'person_id' in vals:
            manager(self.env)
        return super().write(vals)


class Relationship(models.Model):
    _name = 'federation.person.relationship'
    _description = 'Verified Person Relationship'
    _inherit = ['mail.thread']
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    delegate_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    kind = fields.Selection([('guardian', 'Guardian'), ('payer', 'Payer')], required=True)
    valid_from = fields.Date(required=True, default=fields.Date.today)
    valid_until = fields.Date(required=True)
    state = fields.Selection([('draft', 'Not verified'), ('verified', 'Verified'), ('revoked', 'Revoked')], default='draft', required=True, readonly=True, tracking=True)
    verified_by_id = fields.Many2one('res.users', readonly=True)
    reason = fields.Text(required=True)

    @api.constrains('valid_from', 'valid_until', 'person_id', 'delegate_id')
    def _check_scope(self):
        for r in self:
            if r.valid_until < r.valid_from or r.person_id == r.delegate_id:
                raise ValidationError(_('Check relationship dates and identities.'))

    @api.model_create_multi
    def create(self, vals_list):
        manager(self.env)
        if any(v.get('state', 'draft') != 'draft' or v.get('verified_by_id') for v in vals_list):
            raise AccessError(_('Use Verify to activate a relationship.'))
        return super().create(vals_list)

    def write(self, vals):
        manager(self.env)
        if 'state' in vals or 'verified_by_id' in vals:
            raise AccessError(_('Use relationship commands.'))
        if any(r.state == 'verified' for r in self):
            raise ValidationError(_('Revoke a verified relationship before changing its scope.'))
        return super().write(vals)

    def action_verify(self):
        manager(self.env)
        self.check_access('write')
        if not self:
            return True
        self.env.cr.execute('SELECT id FROM federation_person_relationship WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
        self.invalidate_recordset()
        self.check_access('write')
        if any(r.state != 'draft' or r.valid_until < fields.Date.today() for r in self):
            raise ValidationError(_('Only unverified relationships can be verified.'))
        return super().write({'state': 'verified', 'verified_by_id': self.env.uid})

    def action_revoke(self):
        manager(self.env)
        self.check_access('write')
        if not self:
            return True
        self.env.cr.execute('SELECT id FROM federation_person_relationship WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
        self.invalidate_recordset()
        self.check_access('write')
        return super().write({'state': 'revoked', 'verified_by_id': False})


class Membership(models.Model):
    _name = 'federation.person.membership'
    _description = 'Season Membership'
    _inherit = ['mail.thread']
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    club_id = fields.Many2one('federation.club', required=True, ondelete='restrict', index=True)
    season_id = fields.Many2one('federation.season', required=True, ondelete='restrict', index=True)
    role = fields.Selection([('player', 'Player'), ('coach', 'Coach'), ('official', 'Official'), ('volunteer', 'Volunteer')], required=True)
    state = fields.Selection([('draft', 'Needs review'), ('active', 'Active'), ('cancelled', 'Cancelled')], default='draft', required=True, tracking=True)
    review_note = fields.Text()
    previous_id = fields.Many2one('federation.person.membership', ondelete='restrict', readonly=True)
    _membership_unique = models.Constraint('UNIQUE(person_id, club_id, season_id, role)', 'This membership already exists.')

    @api.constrains('previous_id', 'person_id', 'club_id', 'role', 'company_id', 'season_id')
    def _check_renewal_chain(self):
        for row in self.filtered('previous_id'):
            previous = row.previous_id
            if (row.person_id != previous.person_id or row.club_id != previous.club_id
                    or row.role != previous.role or row.company_id != previous.company_id
                    or row.season_id.date_start <= previous.season_id.date_start):
                raise ValidationError(_('Renewal must preserve identity and follow an earlier season.'))

    def write(self, vals):
        manager(self.env)
        if 'previous_id'  in vals:
            raise AccessError(_('Renewal lineage cannot be edited.'))
        if any(r.state == 'active' for r in self) and {'person_id', 'club_id', 'season_id', 'role', 'company_id'} & set(vals):
            raise ValidationError(_('Active membership identity is immutable.'))
        return super().write(vals)

    @api.model
    def _person_ids(self, kind='guardian'):
        if self.env.user._is_public():
            raise AccessError(_('Sign in first.'))
        today = fields.Date.today()
        partner = self.env.user.partner_id
        relationships = self.env['federation.person.relationship'].sudo().search([
            ('company_id', 'in', self.env.companies.ids), ('delegate_id', '=', partner.id), ('kind', '=', kind), ('state', '=', 'verified'),
            ('valid_from', '<=', today), ('valid_until', '>=', today)])
        return list(set([partner.id] + relationships.person_id.ids))

    @api.model
    def _portal_rows(self):
        rows = self.sudo().search([('company_id', 'in', self.env.companies.ids), ('person_id', 'in', self._person_ids())], limit=200)
        return [{'id': r.id, 'person': r.person_id.name, 'club': r.club_id.name,
                 'season': r.season_id.name, 'role': r.role, 'state': r.state,
                 'note': r.review_note or ''} for r in rows]

    def _renew(self, season_id):
        self.ensure_one()
        if not self.sudo().exists() or self.sudo().company_id not in self.env.companies or self.sudo().person_id.id not in self._person_ids():
            raise AccessError(_('This membership is outside your personal scope.'))
        old = self.sudo()
        season = self.env['federation.season'].sudo().browse(int(season_id)).exists()
        if not season or season.state != 'open' or season.date_start <= old.season_id.date_start:
            raise ValidationError(_('Choose a later open season.'))
        self.env.cr.execute('SELECT id FROM federation_person_membership WHERE id=%s FOR UPDATE', [self.id])
        self.env.cr.execute('SELECT id FROM federation_season WHERE id=%s FOR UPDATE', [season.id])
        old.invalidate_recordset()
        season.invalidate_recordset()
        if (old.state != 'active' or not old.club_id.active or season.state != 'open'
                or season.date_start <= old.season_id.date_start or old.company_id not in self.env.companies
                or old.person_id.id not in self._person_ids()):
            raise ValidationError(_('Renew only an active membership in an active club into a later open season.'))
        domain = [('person_id', '=', old.person_id.id), ('club_id', '=', old.club_id.id),
                  ('season_id', '=', season.id), ('role', '=', old.role)]
        existing = self.sudo().search(domain, limit=1)
        if existing:
            return existing.id
        try:
            with self.env.cr.savepoint():
                return self.sudo().create({'person_id': old.person_id.id, 'club_id': old.club_id.id,
                    'season_id': season.id, 'role': old.role, 'previous_id': old.id, 'company_id': old.company_id.id}).id
        except IntegrityError as error:
            if error.pgcode != '23505':
                raise
            raise SerializationFailure('Concurrent renewal; retry transaction') from error


class Request(models.Model):
    _name = 'federation.person.request'
    _description = 'Scoped Personal Document Request'
    _inherit = ['mail.thread']
    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    guardian_required = fields.Boolean(default=False)
    deadline = fields.Date(required=True)
    purpose = fields.Text(required=True)
    state = fields.Selection([('requested', 'Requested'), ('uploaded', 'Uploaded, awaiting review'),
        ('verified', 'Verified for this request'), ('returned', 'Replacement requested'), ('cancelled', 'Cancelled')],
        default='requested', required=True, readonly=True, tracking=True)
    document = fields.Binary(attachment=True, groups='sports_federation_base.group_federation_manager')
    filename = fields.Char(groups='sports_federation_base.group_federation_manager')
    review_note = fields.Text()
    uploaded_by_id = fields.Many2one('res.users', readonly=True)
    verified_by_id = fields.Many2one('res.users', readonly=True)
    valid_until = fields.Date()
    document_revision = fields.Integer(default=0, readonly=True, copy=False)
    document_checksum = fields.Char(readonly=True, copy=False)
    verified_revision = fields.Integer(readonly=True, copy=False)
    verified_on = fields.Datetime(readonly=True, copy=False)

    def _allowed(self):
        self.ensure_one()
        if not self.sudo().exists() or self.sudo().company_id not in self.env.companies:
            return False
        person = self.sudo().person_id.id
        if self.sudo().guardian_required:
            membership = self.env['federation.person.membership']
            ids = membership._person_ids()
            # Self access is not sufficient when a guardian is explicitly required.
            return person in ids and person != self.env.user.partner_id.id
        return person in self.env['federation.person.membership']._person_ids()

    @api.model
    def _portal_rows(self):
        ids = self.env['federation.person.membership']._person_ids()
        rows = self.sudo().search([('company_id', 'in', self.env.companies.ids), ('person_id', 'in', ids)], limit=200)
        return [{'id': r.id, 'name': r.name, 'purpose': r.purpose, 'state': r.state,
            'deadline': r.deadline, 'note': r.review_note or '', 'can_upload': r.with_user(self.env.user)._allowed()
            and r.state in ('requested', 'returned')} for r in rows]

    def _upload(self, upload):
        self.ensure_one()
        if not self._allowed():
            raise AccessError(_('You are not authorised for this document request.'))
        self.env.cr.execute('SELECT id FROM federation_person_request WHERE id=%s FOR UPDATE', [self.id])
        record = self.sudo()
        record.invalidate_recordset()
        if not record.with_user(self.env.user)._allowed():
            raise AccessError(_('Document access changed.'))
        if record.state not in ('requested', 'returned'):
            raise ValidationError(_('This request is no longer accepting uploads.'))
        if not upload:
            raise ValidationError(_('Select a document.'))
        policy = self.env['federation.attachment.policy']
        maximum = policy.get_policy('portal_document')['max_bytes']
        payload = upload.read(maximum + 1)
        checked = policy.validate_upload('portal_document', upload.filename, payload, mimetype=upload.content_type)
        # Bypass only the command-field guard after actor, scope and state validation.
        super(Request, record).write({'document': base64.b64encode(checked['payload']),
             'filename': upload.filename, 'state': 'uploaded', 'uploaded_by_id': self.env.uid,
            'document_revision': record.document_revision + 1,
            'document_checksum': hashlib.sha256(checked['payload']).hexdigest(),
            'verified_by_id': False, 'verified_revision': 0, 'verified_on': False})
        record.message_post(body=_('Uploaded revision %(revision)s; checksum %(checksum)s.') % {
            'revision': record.document_revision, 'checksum': record.document_checksum})

    def write(self, vals):
        manager(self.env)
        if {'state', 'document', 'uploaded_by_id', 'verified_by_id', 'document_revision', 'document_checksum', 'verified_revision', 'verified_on'} & set(vals):
            raise AccessError(_('Use the request workflow commands.'))
        if any(r.state in ('uploaded', 'verified') for r in self) and {'person_id', 'guardian_required', 'purpose', 'company_id', 'valid_until'} & set(vals):
            raise ValidationError(_('Reviewed request scope is immutable.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        manager(self.env)
        if any(v.get('state', 'requested') != 'requested' or any(v.get(k) for k in ('document', 'uploaded_by_id', 'verified_by_id', 'document_revision', 'document_checksum', 'verified_revision', 'verified_on')) for v in vals_list):
            raise AccessError(_('Create an empty request first.'))
        return super().create(vals_list)

    def _review_lock(self):
        manager(self.env)
        self.ensure_one()
        self.check_access('write')
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM federation_person_request WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        self.check_access('write')

    def action_verify(self):
        self._review_lock()
        if self.state != 'uploaded' or not self.document or self.uploaded_by_id.id == self.env.uid:
            raise ValidationError(_('Independent review of an uploaded document is required.'))
        checksum = hashlib.sha256(base64.b64decode(self.document)).hexdigest()
        if not self.document_revision or not self.document_checksum:
            super().write({'document_revision': max(1, self.document_revision), 'document_checksum': checksum})
        if checksum != self.document_checksum:
            raise ValidationError(_('Document checksum mismatch. Request replacement.'))
        wizard = self.env['federation.person.request.review'].create({'request_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': wizard._name, 'res_id': wizard.id,
                'view_mode': 'form', 'target': 'new', 'name': _('Review exact document revision')}

    def _verify_revision(self, revision, checksum):
        self._review_lock()
        if self.valid_until and self.valid_until < fields.Date.today():
            raise ValidationError(_('Expired evidence requires replacement.'))
        actual = hashlib.sha256(base64.b64decode(self.document or b'')).hexdigest()
        if (self.state != 'uploaded' or not self.document or self.uploaded_by_id.id == self.env.uid
                or self.document_revision != revision or self.document_checksum != checksum or actual != checksum):
            raise ValidationError(_('The reviewed document changed. Inspect the current revision.'))
        super().write({'state': 'verified', 'verified_by_id': self.env.uid,
                       'verified_revision': revision, 'verified_on': fields.Datetime.now()})
        self.message_post(body=_('Verified revision %(revision)s; checksum %(checksum)s.') % {
            'revision': revision, 'checksum': checksum})
        return True

    def action_return(self):
        for record in self.sorted('id'):
            record._review_lock()
            if record.state not in ('uploaded', 'verified') or not record.review_note:
                raise ValidationError(_('Explain the required replacement.'))
            record.message_post(body=_('Returned revision %(revision)s; checksum %(checksum)s. Previous approval remains in chatter history.') % {
                'revision': record.document_revision, 'checksum': record.document_checksum or ''})
            super(Request, record).write({'state': 'returned', 'verified_by_id': False,
                                          'verified_revision': 0, 'verified_on': False})
        return True


class RequestReview(models.TransientModel):
    _name = 'federation.person.request.review'
    _description = 'Exact Document Revision Review'
    request_id = fields.Many2one('federation.person.request', required=True, readonly=True)
    revision = fields.Integer(readonly=True)
    checksum = fields.Char(readonly=True)
    document = fields.Binary(readonly=True, attachment=False)
    filename = fields.Char(readonly=True)
    inspected = fields.Boolean(string='I inspected this exact document revision')

    @api.model_create_multi
    def create(self, vals_list):
        manager(self.env)
        prepared = []
        for vals in vals_list:
            request = self.env['federation.person.request'].browse(vals['request_id'])
            request._review_lock()
            if request.state != 'uploaded' or request.uploaded_by_id.id == self.env.uid:
                raise ValidationError(_('Independent review is required.'))
            prepared.append({'request_id': request.id, 'revision': request.document_revision,
                             'checksum': request.document_checksum, 'document': request.document,
                             'filename': request.filename, 'inspected': False})
        return super().create(prepared)

    def write(self, vals):
        manager(self.env)
        if set(vals) - {'inspected'}:
            raise AccessError(_('Review snapshots cannot be edited.'))
        return super().write(vals)

    def action_confirm(self):
        self.ensure_one()
        self.check_access('read')
        if self.create_uid != self.env.user or not self.inspected:
            raise ValidationError(_('Inspect the document in your own review dialog.'))
        self.request_id._verify_revision(self.revision, self.checksum)
        return {'type': 'ir.actions.act_window_close'}
