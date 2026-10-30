from datetime import timedelta
from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install', 'sf_member_services')
class TestPersonalScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['res.users'].create({'name': 'Membership reviewer', 'login': 'member_reviewer',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
            cls.env.ref('sports_federation_base.group_federation_manager').id])]})
        cls.portal = cls.env['res.users'].create({'name': 'Personal portal', 'login': 'member_portal',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])]})
        cls.child = cls.env['res.partner'].create({'name': 'Scoped person'})

    def relationship(self, kind='guardian', expired=False):
        today = fields.Date.today()
        row = self.env['federation.person.relationship'].with_user(self.manager).create({
            'person_id': self.child.id, 'delegate_id': self.portal.partner_id.id, 'kind': kind,
            'valid_from': today - timedelta(days=20),
            'valid_until': today - timedelta(days=1) if expired else today + timedelta(days=20),
            'reason': 'Test identity evidence'})
        row.action_verify()
        return row

    def test_payer_is_not_guardian(self):
        self.relationship('payer')
        ids = self.env['federation.person.membership'].with_user(self.portal)._person_ids()
        self.assertNotIn(self.child.id, ids)

    def test_guardian_scope_and_revocation(self):
        row = self.relationship()
        service = self.env['federation.person.membership'].with_user(self.portal)
        self.assertIn(self.child.id, service._person_ids())
        row.action_revoke()
        self.assertNotIn(self.child.id, service._person_ids())

    def test_expired_guardian_does_not_grant_scope(self):
        self.relationship(expired=True)
        self.assertNotIn(self.child.id, self.env['federation.person.membership'].with_user(self.portal)._person_ids())

    def test_verified_relationship_cannot_be_retargeted(self):
        row = self.relationship()
        with self.assertRaises(ValidationError):
            row.write({'kind': 'payer'})
        with self.assertRaises(AccessError):
            row.write({'state': 'draft'})

    def test_portal_cannot_verify_relationship(self):
        row = self.relationship()
        with self.assertRaises(AccessError):
            row.with_user(self.portal).action_revoke()
