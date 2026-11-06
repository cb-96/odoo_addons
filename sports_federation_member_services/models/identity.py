from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .membership import manager
from .lifecycle import command, guarded, lock
from ..lifecycle_policy import fingerprint, match_candidate, normal_name


class IdentityAudit(models.Model):
    _name = 'federation.identity.decision'
    _description = 'Immutable Reviewed Identity Decision'
    company_id = fields.Many2one('res.company', required=True)
    player_id = fields.Many2one('federation.player', required=True, ondelete='restrict')
    duplicate_player_id = fields.Many2one('federation.player', ondelete='restrict')
    person_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    actor_id = fields.Many2one('res.users', required=True)
    reason = fields.Text(required=True)
    before = fields.Json(required=True)
    decided_on = fields.Datetime(default=fields.Datetime.now, required=True)

    @api.model_create_multi
    def create(self, vals_list):
        guarded(self.env)
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_('Identity decisions are immutable.'))

    def unlink(self):
        raise AccessError(_('Identity history must be retained.'))


class IdentityPlayer(models.Model):
    _inherit = 'federation.player'
    family_duplicate_of_id = fields.Many2one('federation.player', ondelete='restrict', copy=False,
                                            groups='sports_federation_base.group_federation_manager')

    family_match_key = fields.Char(copy=False, readonly=True, index=True)
    _family_match_unique = models.Constraint('unique(family_match_key)', 'A reviewed matching identity already exists.')

    @api.model_create_multi
    def create(self, vals_list):
        batch_keys = set()
        for vals in vals_list:
            if 'family_match_key' in vals:
                guarded(self.env)
            if vals.get('family_duplicate_of_id'):
                guarded(self.env)
            if vals.get('person_id'):
                guarded(self.env)
                person = self.env['res.partner'].sudo().browse(vals['person_id'])
                lock(person)
                if person.family_canonical_id:
                    raise ValidationError(_('Use the canonical identity.'))
            if vals.get('birth_date'):
                key = fingerprint((normal_name(vals.get('first_name')), normal_name(vals.get('last_name')), str(vals['birth_date'])))
                if key in batch_keys:
                    raise ValidationError(_('The batch contains duplicate identities.'))
                batch_keys.add(key)
                vals['family_match_key'] = key
                self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [int(key[:15], 16)])
                candidates = self.sudo().search([('birth_date', '=', vals['birth_date']), ('family_duplicate_of_id', '=', False)])
                if any(match_candidate(vals.get('first_name'), vals.get('last_name'), vals['birth_date'], {
                        'first_name': p.first_name, 'last_name': p.last_name, 'birthdate': p.birth_date}) for p in candidates):
                    raise ValidationError(_('A matching player identity exists. Federation staff must review it before creating another record.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'family_match_key' in vals:
            guarded(self.env)
        if 'family_duplicate_of_id' in vals:
            guarded(self.env)
        if any(self.sudo().mapped('family_duplicate_of_id')) and (vals.get('state') == 'active' or vals.get('person_id')):
            raise ValidationError(_('A resolved duplicate cannot be reactivated or relinked. Use its canonical player.'))
        if 'person_id' in vals:
            guarded(self.env)
        if {'first_name', 'last_name', 'birth_date'} & vals.keys():
            for row in self:
                date = vals.get('birth_date', row.birth_date)
                key = fingerprint((normal_name(vals.get('first_name', row.first_name)), normal_name(vals.get('last_name', row.last_name)), str(date))) if date and not row.sudo().family_duplicate_of_id else False
                super(IdentityPlayer, row).write(dict(vals, family_match_key=key))
            return True
        return super().write(vals)

    def action_review_identity(self):
        manager(self.env)
        self.ensure_one()
        self.check_access('read')
        review = self.env['federation.identity.review'].create({'player_id': self.id, 'person_id': self.person_id.id})
        return {'type': 'ir.actions.act_window', 'res_model': review._name, 'res_id': review.id,
                'view_mode': 'form', 'target': 'new', 'name': _('Review identity, preserve history')}


class IdentityReview(models.TransientModel):
    _name = 'federation.identity.review'
    _description = 'Reviewed Player Identity Matching'
    player_id = fields.Many2one('federation.player', required=True)
    person_id = fields.Many2one('res.partner', required=False)
    duplicate_player_id = fields.Many2one('federation.player')
    reason = fields.Text(required=False)
    inspected = fields.Boolean(string='I reviewed identity evidence and the listed effects')
    preview_signature = fields.Char(readonly=True)
    preview = fields.Json(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        manager(self.env)
        return super().create([{key: value for key, value in vals.items() if key in ('player_id', 'person_id', 'duplicate_player_id', 'reason')} for vals in vals_list])

    def _snapshot(self):
        self.ensure_one()
        manager(self.env)
        self.check_access('write')
        if self.create_uid != self.env.user:
            raise AccessError(_('Use your own identity review dialog.'))
        player, person, duplicate = self.player_id, self.person_id, self.duplicate_player_id
        if not person or player.family_duplicate_of_id or person.family_canonical_id or player == duplicate:
            raise ValidationError(_('Choose a canonical player and existing person; duplicate must be different.'))
        for record in player | duplicate:
            record.check_access('write')
        person.check_access('write')
        if person.company_id and person.company_id not in self.env.companies:
            raise AccessError(_('Canonical person belongs to another company.'))
        if player.person_id and player.person_id != person:
            raise ValidationError(_('Canonical player is already linked to a different person.'))
        old = duplicate.person_id if duplicate else self.env['res.partner'].browse()
        if old and old != person and old.user_ids.filtered('active'):
            raise ValidationError(_('Duplicate identity has an active login. Resolve the account ownership separately before consolidation.'))
        if duplicate and duplicate.family_duplicate_of_id:
            raise ValidationError(_('This duplicate is already resolved.'))
        members = self.env['federation.person.membership'].sudo().search([('person_id', 'in', (person | old).ids)])
        docs = self.env['federation.person.request'].sudo().search([('person_id', 'in', (person | old).ids)])
        relationships = self.env['federation.person.relationship'].sudo().search([('person_id', 'in', (person | old).ids)])
        if any(record.company_id not in self.env.companies for record in members):
            raise AccessError(_('Identity has membership history in another company. Use an authorised cross-company review.'))
        if any(doc.company_id not in self.env.companies for doc in docs) or any(rel.company_id not in self.env.companies for rel in relationships):
            raise AccessError(_('Identity has document or relationship history outside your company scope.'))
        keys = set()
        for member in members:
            key = (member.club_id.id, member.season_id.id, member.role)
            if key in keys:
                raise ValidationError(_('Overlapping memberships need an explicit history decision before identity consolidation. Nothing is deleted.'))
            keys.add(key)
        return {'player': [(p.id, p.person_id.id, p.state, p.first_name, p.last_name, str(p.birth_date), str(p.write_date)) for p in player | duplicate],
                'people': [(p.id, str(p.write_date)) for p in person | old],
                'memberships': [(m.id, m.person_id.id, m.lifecycle_revision, str(m.write_date)) for m in members],
                'documents': [(d.id, d.person_id.id, d.document_revision, d.document_checksum, d.state, str(d.write_date)) for d in docs],
                'relationships': [(r.id, r.state, str(r.write_date)) for r in relationships],
                'effects': _('Retain both player records and all licences/results. Retire the duplicate player. Move non-overlapping service history to the canonical person. Revoke duplicate-person delegations; never union permissions. Return moved evidence for independent re-review. Invoices and login accounts are not merged.')}

    def action_preview(self):
        snapshot = self._snapshot()
        command(self).write({'preview': snapshot, 'preview_signature': fingerprint(snapshot), 'inspected': False})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    def write(self, vals):
        manager(self.env)
        if {'preview', 'preview_signature'} & vals.keys():
            guarded(self.env)
        return super().write(vals)

    def action_confirm(self):
        manager(self.env)
        self.ensure_one()
        lock(self.person_id | self.duplicate_player_id.person_id)
        lock(self.player_id | self.duplicate_player_id)
        for model in ('federation.person.membership', 'federation.person.request', 'federation.person.relationship'):
            lock(self.env[model].search([('person_id', 'in', (self.person_id | self.duplicate_player_id.person_id).ids)]))
        snapshot = self._snapshot()
        if not self.inspected or not self.reason or not self.preview_signature or fingerprint(snapshot) != self.preview_signature:
            raise ValidationError(_('Inspect a fresh preview and record the identity decision reason.'))
        player, duplicate, person = self.player_id, self.duplicate_player_id, self.person_id
        old = duplicate.person_id if duplicate else self.env['res.partner'].browse()
        if old and old != person:
            members = self.env['federation.person.membership'].search([('person_id', '=', old.id)])
            docs = self.env['federation.person.request'].search([('person_id', '=', old.id)])
            for relation in self.env['federation.person.relationship'].search([('person_id', '=', old.id), ('state', '!=', 'revoked')]):
                relation.action_revoke()
            for member in members:
                command(member).write({'person_id': person.id})
            # Existing request metadata guard is bypassed only in this audited identity command.
            from .membership import Request
            for doc in docs:
                doc._archive_current()
                super(Request, doc).write({'person_id': person.id, 'state': 'returned',
                    'verified_by_id': False, 'verified_revision': 0, 'verified_on': False,
                    'review_note': _('Identity consolidated: submit current evidence for independent re-review.')})
                doc.message_post(body=_('Identity changed through a reviewed decision. Previous document bytes and revision are retained.'))
            command(old).write({'family_canonical_id': person.id, 'family_reference': False})
        if duplicate:
            command(duplicate).write({'person_id': False, 'state': 'inactive', 'family_duplicate_of_id': player.id, 'family_match_key': False})
        command(player).write({'person_id': person.id, 'family_match_key': fingerprint((normal_name(player.first_name), normal_name(player.last_name), str(player.birth_date))) if player.birth_date else False})
        command(self.env['federation.identity.decision']).create({
            'company_id': self.env.company.id, 'player_id': player.id, 'duplicate_player_id': duplicate.id,
            'person_id': person.id, 'actor_id': self.env.uid, 'reason': self.reason, 'before': snapshot})
        return {'type': 'ir.actions.act_window_close'}
