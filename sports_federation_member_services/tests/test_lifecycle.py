from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from werkzeug.datastructures import FileStorage
from odoo import fields
from odoo.tests import TransactionCase, HttpCase, tagged
from odoo.exceptions import AccessError, ValidationError


class FamilyFixture:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.reviewer = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Lifecycle reviewer', 'login': 'lifecycle-reviewer', 'password': 'family-test',
            'group_ids': [(6, 0, [env.ref('base.group_user').id, env.ref('sports_federation_base.group_federation_manager').id])]})
        cls.guardian = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Lifecycle guardian', 'login': 'lifecycle-guardian', 'password': 'family-test',
            'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
        cls.child_a = env['res.partner'].create({'name': 'Dependant Alpha'})
        cls.child_b = env['res.partner'].create({'name': 'Dependant Beta'})
        cls.club = env['federation.club'].create({'name': 'Lifecycle club'})
        today = fields.Date.today()
        cls.season = env['federation.season'].create({'name': 'Lifecycle current', 'date_start': today - timedelta(days=30), 'date_end': today + timedelta(days=30), 'state': 'open'})
        cls.next_season = env['federation.season'].create({'name': 'Lifecycle next', 'date_start': today + timedelta(days=31), 'date_end': today + timedelta(days=365), 'state': 'open'})
        cls.memberships = env['federation.person.membership'].with_user(cls.reviewer).create([
            {'person_id': child.id, 'club_id': cls.club.id, 'season_id': cls.season.id, 'role': 'player', 'review_note': 'Reviewed membership fixture'} for child in (cls.child_a, cls.child_b)])
        cls.memberships.action_activate()
        cls.relationships = env['federation.person.relationship'].with_user(cls.reviewer).create([
            {'person_id': child.id, 'delegate_id': cls.guardian.partner_id.id, 'kind': 'guardian',
             'valid_from': today - timedelta(days=1), 'valid_until': today + timedelta(days=366), 'reason': 'Reviewed fixture evidence'} for child in (cls.child_a, cls.child_b)])
        cls.relationships.action_verify()

    def document(self, person=None, **values):
        return self.env['federation.person.request'].with_user(self.reviewer).create({
            'name': 'Required evidence', 'person_id': (person or self.child_a).id,
            'purpose': 'Membership evidence review', 'guardian_required': True, **values})

    def upload(self, document, payload=b'%PDF-1.4 fixture evidence'):
        upload = FileStorage(stream=BytesIO(payload), filename='evidence.pdf', content_type='application/pdf')
        policy_class = type(self.env['federation.attachment.policy'])
        with patch.object(policy_class, 'validate_upload', return_value={'payload': payload}):
            document.with_user(self.guardian)._upload(upload)

    def identity(self, player, person, duplicate=None):
        wizard = self.env['federation.identity.review'].with_user(self.reviewer).create({
            'player_id': player.id, 'person_id': person.id, 'duplicate_player_id': duplicate.id if duplicate else False,
            'reason': 'Reviewed matching evidence'})
        wizard.action_preview()
        wizard.inspected = True
        return wizard


@tagged('post_install', '-at_install', 'sf_member_lifecycle')
class TestMemberLifecycle(FamilyFixture, TransactionCase):
    def test_two_dependants_separate_records(self):
        rows = self.env['federation.family.summary'].with_user(self.guardian)._rows()
        a = next(row for row in rows if row['id'] == self.child_a.id)
        b = next(row for row in rows if row['id'] == self.child_b.id)
        self.assertEqual(a['memberships'][0]['person_id'], self.child_a.id)
        self.assertEqual(b['memberships'][0]['person_id'], self.child_b.id)
        self.assertNotEqual(a['memberships'][0]['id'], b['memberships'][0]['id'])

    def test_wrong_person_membership_action_rejected(self):
        with self.assertRaises(AccessError): self.memberships[0].with_user(self.guardian)._assert_person(self.child_b.id)

    def test_renewal_is_draft_not_activation(self):
        result = self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        renewed = self.env['federation.person.membership'].browse(result)
        self.assertEqual(renewed.state, 'draft')
        self.assertEqual(renewed.previous_id, self.memberships[0])
        self.assertFalse(self.env['federation.player.license'].search([('season_id', '=', self.next_season.id)]))

    def test_renewal_replay_one_record(self):
        first = self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        self.assertEqual(first, self.memberships[0].with_user(self.guardian)._renew(self.next_season.id))

    def test_renewal_copies_requirement_not_evidence(self):
        doc = self.document(membership_id=self.memberships[0].id, required_for_activation=True)
        self.upload(doc)
        result = self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        copy = self.env['federation.person.request'].search([('membership_id', '=', result)])
        self.assertEqual(copy.renewed_from_id, doc)
        self.assertEqual(copy.state, 'requested')
        self.assertFalse(copy.document)
        self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        self.assertEqual(self.env['federation.person.request'].search_count([('membership_id', '=', result)]), 1)

    def test_required_document_blocks_membership_activation(self):
        result = self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        renewed = self.env['federation.person.membership'].with_user(self.reviewer).browse(result)
        renewed.review_note = 'Reviewed membership'
        self.document(membership_id=renewed.id, required_for_activation=True)
        with self.assertRaises(ValidationError): renewed.action_activate()

    def test_raw_activation_denied(self):
        with self.assertRaises(AccessError): self.memberships[0].write({'state': 'active'})

    def test_review_note_required_for_activation(self):
        row = self.env['federation.person.membership'].with_user(self.reviewer).create({
            'person_id': self.child_a.id, 'club_id': self.club.id, 'season_id': self.next_season.id, 'role': 'coach'})
        with self.assertRaises(ValidationError): row.action_activate()

    def test_revoked_guardian_cannot_renew(self):
        self.relationships[0].action_revoke()
        with self.assertRaises(AccessError): self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)

    def test_revoked_guardian_cannot_upload(self):
        doc = self.document()
        self.relationships[0].action_revoke()
        with self.assertRaises(AccessError): self.upload(doc)

    def test_revoked_guardian_not_in_summary(self):
        self.relationships[0].action_revoke()
        with self.assertRaises(AccessError): self.env['federation.family.summary'].with_user(self.guardian)._rows(self.child_a.id)

    def test_payer_does_not_gain_document_scope(self):
        self.relationships.action_revoke()
        today = fields.Date.today()
        payer = self.env['federation.person.relationship'].with_user(self.reviewer).create({
            'person_id': self.child_a.id, 'delegate_id': self.guardian.partner_id.id, 'kind': 'payer',
            'valid_from': today, 'valid_until': today + timedelta(days=10), 'reason': 'Payer only'})
        payer.action_verify()
        self.assertFalse(self.document().with_user(self.guardian)._allowed())

    def test_stale_document_snapshot_rejected(self):
        doc = self.document()
        self.upload(doc)
        action = doc.action_verify()
        review = self.env['federation.person.request.review'].with_user(self.reviewer).browse(action['res_id'])
        review.inspected = True
        doc.review_note = 'Replace the unreadable page'
        doc.action_return()
        self.upload(doc, b'%PDF-1.4 replacement evidence')
        with self.assertRaises(ValidationError): review.action_confirm()

    def test_verified_document_does_not_activate_membership(self):
        result = self.memberships[0].with_user(self.guardian)._renew(self.next_season.id)
        doc = self.document(membership_id=result, required_for_activation=True)
        self.upload(doc)
        action = doc.action_verify()
        review = self.env['federation.person.request.review'].with_user(self.reviewer).browse(action['res_id'])
        review.inspected = True
        review.action_confirm()
        self.assertEqual(self.env['federation.person.membership'].browse(result).state, 'draft')

    def test_document_wrong_membership_person_rejected(self):
        with self.assertRaises(ValidationError): self.document(membership_id=self.memberships[1].id)

    def test_licence_request_reuses_unique_draft(self):
        player = self.env['federation.player'].create({'first_name': 'Licence', 'last_name': 'Fixture', 'club_id': self.club.id})
        self.identity(player, self.child_a).action_confirm()
        first = self.memberships[0].with_user(self.guardian)._request_licence(self.child_a.id)
        self.assertEqual(first, self.memberships[0].with_user(self.guardian)._request_licence(self.child_a.id))
        self.assertEqual(self.env['federation.player.license'].browse(first).state, 'draft')

    def test_parental_upload_creates_draft_not_approval(self):
        player = self.env['federation.player'].create({'first_name': 'Parental', 'last_name': 'Fixture', 'club_id': self.club.id})
        self.identity(player, self.child_a).action_confirm()
        doc = self.document(purpose_kind='parental')
        self.upload(doc)
        self.assertEqual(doc.parental_approval_id.player_id, player)
        self.assertEqual(doc.parental_approval_id.state, 'draft')
        self.assertFalse(doc._current_verified())
        with self.assertRaises(ValidationError): doc._verify_revision(doc.document_revision, doc.document_checksum)

    def test_cancel_request_does_not_cancel_before_review(self):
        change_id = self.memberships[0].with_user(self.guardian)._request_change('cancel', self.child_a.id, 'Requested cancellation')
        self.assertEqual(self.memberships[0].state, 'active')
        change = self.env['federation.member.change'].with_user(self.reviewer).browse(change_id)
        change.decision_note = 'Reviewed cancellation'
        change.action_approve()
        self.assertEqual(self.memberships[0].state, 'cancelled')

    def test_lifecycle_request_replay_one_request(self):
        row = self.memberships[0].with_user(self.guardian)
        first = row._request_change('cancel', self.child_a.id, 'Cancel')
        self.assertEqual(first, row._request_change('cancel', self.child_a.id, 'Cancel'))

    def test_stale_lifecycle_decision_rejected(self):
        change_id = self.memberships[0].with_user(self.guardian)._request_change('cancel', self.child_a.id, 'Cancel')
        self.memberships[0].review_note = 'New source review'
        change = self.env['federation.member.change'].with_user(self.reviewer).browse(change_id)
        change.decision_note = 'Old review'
        with self.assertRaises(ValidationError): change.action_approve()

    def test_reactivation_returns_to_review_not_active(self):
        row = self.memberships[0].with_user(self.guardian)
        change = self.env['federation.member.change'].with_user(self.reviewer).browse(row._request_change('cancel', self.child_a.id, 'Cancel'))
        change.decision_note = 'Cancel reviewed'; change.action_approve()
        reactivate = self.env['federation.member.change'].with_user(self.reviewer).browse(row._request_change('reactivate', self.child_a.id, 'Return'))
        reactivate.decision_note = 'Reactivation review'; reactivate.action_approve()
        self.assertEqual(row.sudo().state, 'draft')

    def test_transfer_retains_source_and_creates_draft(self):
        destination = self.env['federation.club'].create({'name': 'Destination club'})
        change = self.env['federation.member.change'].with_user(self.reviewer).browse(
            self.memberships[0].with_user(self.guardian)._request_change('transfer', self.child_a.id, 'Transfer request', destination.id))
        change.decision_note = 'Membership transfer only'; change.action_approve()
        self.assertEqual(self.memberships[0].state, 'cancelled')
        self.assertEqual(change.result_membership_id.state, 'draft')
        self.assertEqual(change.result_membership_id.club_id, destination)

    def test_reviewed_identity_link_no_new_person(self):
        player = self.env['federation.player'].create({'first_name': 'Link', 'last_name': 'Fixture'})
        count = self.env['res.partner'].search_count([])
        self.identity(player, self.child_a).action_confirm()
        self.assertEqual(player.person_id, self.child_a)
        self.assertEqual(self.env['res.partner'].search_count([]), count)

    def test_identity_stale_preview_rejected(self):
        player = self.env['federation.player'].create({'first_name': 'Stale', 'last_name': 'Fixture'})
        wizard = self.identity(player, self.child_a)
        player.last_name = 'Changed'
        with self.assertRaises(ValidationError): wizard.action_confirm()

    def test_duplicate_resolution_preserves_both_players(self):
        canonical = self.env['federation.player'].create({'first_name': 'Canonical', 'last_name': 'Fixture'})
        duplicate = self.env['federation.player'].create({'first_name': 'Duplicate', 'last_name': 'Fixture'})
        legacy = self.env['res.partner'].create({'name': 'Legacy duplicate identity'})
        history = self.env['federation.person.membership'].with_user(self.reviewer).create({'person_id': legacy.id, 'club_id': self.club.id, 'season_id': self.season.id, 'role': 'coach'})
        self.identity(duplicate, legacy).action_confirm()
        self.identity(canonical, self.child_a, duplicate).action_confirm()
        self.assertEqual(history.person_id, self.child_a)
        self.assertTrue(duplicate.exists())
        self.assertEqual(duplicate.family_duplicate_of_id, canonical)
        self.assertEqual(duplicate.state, 'inactive')
        self.assertFalse(duplicate.person_id)
        self.assertTrue(self.env['federation.identity.decision'].search([('duplicate_player_id', '=', duplicate.id)]))

    def test_duplicate_cannot_reactivate(self):
        canonical = self.env['federation.player'].create({'first_name': 'Retained', 'last_name': 'Fixture'})
        duplicate = self.env['federation.player'].create({'first_name': 'Retired', 'last_name': 'Fixture'})
        self.identity(canonical, self.child_a, duplicate).action_confirm()
        with self.assertRaises(ValidationError): duplicate.action_activate()

    def test_normalised_matching_prevents_duplicate(self):
        self.env['federation.player'].create({'first_name': 'Match', 'last_name': 'Fixture', 'birth_date': '2000-01-01'})
        with self.assertRaises(ValidationError):
            self.env['federation.player'].create({'first_name': ' MATCH ', 'last_name': 'fixture', 'birth_date': '2000-01-01'})

    def test_same_batch_matching_prevents_duplicate(self):
        with self.assertRaises(ValidationError): self.env['federation.player'].create([
            {'first_name': 'Batch', 'last_name': 'Fixture', 'birth_date': '2001-01-01'},
            {'first_name': 'batch', 'last_name': 'Fixture', 'birth_date': '2001-01-01'}])

    def test_guardian_cannot_read_identity_audit(self):
        with self.assertRaises(AccessError): self.env['federation.identity.decision'].with_user(self.guardian).search([])

    def test_cross_company_document_denied(self):
        company = self.env['res.company'].create({'name': 'Other lifecycle company'})
        doc = self.env['federation.person.request'].sudo().create({'name': 'Other company evidence',
            'person_id': self.child_a.id, 'company_id': company.id, 'purpose': 'Other company review'})
        self.assertFalse(doc.with_user(self.guardian)._allowed())

    def test_guardian_claim_requires_independent_review(self):
        self.child_a.with_user(self.reviewer).action_issue_family_reference()
        policy_class = type(self.env['federation.attachment.policy'])
        with patch.object(policy_class, 'validate_upload', return_value={'payload': b'%PDF-1.4 claim'}):
            claim_id = self.env['federation.guardian.claim'].with_user(self.guardian)._submit_claim(
                self.child_a.family_reference, 'Guardian relationship evidence',
                FileStorage(stream=BytesIO(b'%PDF-1.4 claim'), filename='claim.pdf', content_type='application/pdf'))
        claim = self.env['federation.guardian.claim'].with_user(self.reviewer).browse(claim_id)
        self.assertEqual(claim.state, 'pending')
        claim.write({'decision_note': 'Reviewed evidence', 'inspected': True})
        claim.action_verify()
        self.assertEqual(claim.relationship_id.state, 'verified')

    def test_evidence_replacement_retains_both_revisions(self):
        doc = self.document()
        self.upload(doc)
        first = doc.document_checksum
        doc.review_note = 'Replacement required'; doc.action_return()
        self.upload(doc, b'%PDF-1.4 second evidence')
        revisions = self.env['federation.member.evidence.revision'].search([('request_id', '=', doc.id)])
        self.assertEqual(len(revisions), 2)
        self.assertIn(first, revisions.mapped('checksum'))
        with self.assertRaises(AccessError): revisions.write({'filename': 'altered.pdf'})

    def test_forged_command_token_rejected(self):
        with self.assertRaises(AccessError): self.memberships[0].with_context(member_lifecycle_token=True).write({'state': 'cancelled'})


@tagged('post_install', '-at_install', 'sf_member_lifecycle')
class TestFamilyHttp(FamilyFixture, HttpCase):
    def test_family_renders_two_dependants(self):
        self.authenticate(self.guardian.login, 'family-test')
        response = self.url_open('/my/family')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dependant Alpha', response.text)
        self.assertIn('Dependant Beta', response.text)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_focus_one_dependant(self):
        self.authenticate(self.guardian.login, 'family-test')
        response = self.url_open('/my/family?person_id=%s' % self.child_a.id)
        self.assertIn('Dependant Alpha', response.text)
        self.assertNotIn('Dependant Beta', response.text)

    def test_revoked_active_session_gets_404(self):
        self.authenticate(self.guardian.login, 'family-test')
        self.relationships[0].action_revoke()
        response = self.url_open('/my/family?person_id=%s' % self.child_a.id)
        self.assertEqual(response.status_code, 404)

    def test_download_other_person_denied(self):
        doc = self.document()
        self.upload(doc)
        self.authenticate(self.guardian.login, 'family-test')
        response = self.url_open('/my/family/requests/%s/download?person_id=%s' % (doc.id, self.child_b.id))
        self.assertEqual(response.status_code, 404)

    def test_mutation_requires_csrf(self):
        self.authenticate(self.guardian.login, 'family-test')
        response = self.url_open('/my/family/memberships/%s/renew' % self.memberships[0].id, data={'season_id': self.next_season.id})
        self.assertEqual(response.status_code, 400)
