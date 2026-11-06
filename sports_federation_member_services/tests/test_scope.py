from io import BytesIO
from datetime import timedelta
from unittest.mock import patch
from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, ValidationError
from werkzeug.datastructures import FileStorage


@tagged("post_install", "-at_install", "sf_member_services")
class TestPersonalScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Membership reviewer",
                "login": "member_reviewer",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "sports_federation_base.group_federation_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.portal = cls.env["res.users"].create(
            {
                "name": "Personal portal",
                "login": "member_portal",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )
        cls.child = cls.env["res.partner"].create({"name": "Scoped person"})

    def relationship(self, kind="guardian", expired=False):
        today = fields.Date.today()
        row = (
            self.env["federation.person.relationship"]
            .with_user(self.manager)
            .create(
                {
                    "person_id": self.child.id,
                    "delegate_id": self.portal.partner_id.id,
                    "kind": kind,
                    "valid_from": today - timedelta(days=20),
                    "valid_until": (
                        today - timedelta(days=1)
                        if expired
                        else today + timedelta(days=20)
                    ),
                    "reason": "Test identity evidence",
                }
            )
        )
        if expired:
            with patch.object(
                fields.Date, "today", return_value=today - timedelta(days=2)
            ):
                row.action_verify()
        else:
            row.action_verify()
        return row

    def test_payer_is_not_guardian(self):
        self.relationship("payer")
        ids = (
            self.env["federation.person.membership"]
            .with_user(self.portal)
            ._person_ids()
        )
        self.assertNotIn(self.child.id, ids)

    def test_guardian_scope_and_revocation(self):
        row = self.relationship()
        service = self.env["federation.person.membership"].with_user(self.portal)
        self.assertIn(self.child.id, service._person_ids())
        row.action_revoke()
        self.assertNotIn(self.child.id, service._person_ids())

    def test_expired_guardian_does_not_grant_scope(self):
        self.relationship(expired=True)
        self.assertNotIn(
            self.child.id,
            self.env["federation.person.membership"]
            .with_user(self.portal)
            ._person_ids(),
        )

    def test_verified_relationship_cannot_be_retargeted(self):
        row = self.relationship()
        with self.assertRaises(ValidationError):
            row.write({"kind": "payer"})
        with self.assertRaises(AccessError):
            row.write({"state": "draft"})

    def test_portal_cannot_verify_relationship(self):
        row = self.relationship()
        with self.assertRaises(AccessError):
            row.with_user(self.portal).action_revoke()

    def test_membership_renewal_is_idempotent(self):
        self.relationship()
        club = self.env["federation.club"].create({"name": "Renewal Club"})
        previous_season = self.env["federation.season"].create(
            {
                "name": "Previous Membership Season",
                "code": "PMS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "state": "closed",
            }
        )
        next_season = self.env["federation.season"].create(
            {
                "name": "Renewal Membership Season",
                "code": "RMS27",
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
                "state": "open",
            }
        )
        membership = self.env["federation.person.membership"].create(
            {
                "person_id": self.child.id,
                "club_id": club.id,
                "season_id": previous_season.id,
                "role": "player",
                "review_note": "Reviewed fixture membership",
            }
        )
        membership.action_activate()

        service_membership = membership.with_user(self.portal)
        renewal_id = service_membership._renew(next_season.id)
        replay_id = service_membership._renew(next_season.id)

        self.assertEqual(replay_id, renewal_id)
        renewal = self.env["federation.person.membership"].browse(renewal_id)
        self.assertEqual(renewal.previous_id, membership)
        self.assertEqual(renewal.state, "draft")

    def test_document_upload_is_one_time_for_guardian_request(self):
        self.relationship()
        request = (
            self.env["federation.person.request"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Membership document request",
                    "person_id": self.child.id,
                    "guardian_required": True,
                    "deadline": fields.Date.today(),
                    "purpose": "Verify a membership document",
                }
            )
        )

        def upload():
            return FileStorage(
                stream=BytesIO(b"%PDF-1.4 membership document"),
                filename="membership.pdf",
                content_type="application/pdf",
            )

        portal_request = request.with_user(self.portal)
        portal_request._upload(upload())
        self.assertEqual(request.state, "uploaded")
        self.assertEqual(request.filename, "membership.pdf")
        self.assertTrue(request.document)
        with self.assertRaises(ValidationError):
            portal_request._upload(upload())

    def _revision_request(self):
        self.relationship()
        request = (
            self.env["federation.person.request"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Revision test",
                    "person_id": self.child.id,
                    "guardian_required": True,
                    "deadline": fields.Date.today(),
                    "purpose": "Revision-bound review",
                }
            )
        )
        request.with_user(self.portal)._upload(
            FileStorage(
                stream=BytesIO(b"%PDF-1.4 first"),
                filename="first.pdf",
                content_type="application/pdf",
            )
        )
        return request

    def test_stale_snapshot_cannot_verify_replacement(self):
        request = self._revision_request()
        action = request.action_verify()
        wizard = (
            self.env["federation.person.request.review"]
            .with_user(self.manager)
            .browse(action["res_id"])
        )
        wizard.write({"inspected": True})
        first_checksum = wizard.checksum
        request.write({"review_note": "Replace document"})
        request.action_return()
        request.with_user(self.portal)._upload(
            FileStorage(
                stream=BytesIO(b"%PDF-1.4 second"),
                filename="second.pdf",
                content_type="application/pdf",
            )
        )
        self.assertEqual(request.document_revision, 2)
        self.assertNotEqual(request.document_checksum, first_checksum)
        with self.assertRaises(ValidationError):
            wizard.action_confirm()
        self.assertEqual(request.state, "uploaded")
        self.assertFalse(request.verified_by_id)

    def test_review_requires_inspection_and_records_revision(self):
        request = self._revision_request()
        action = request.action_verify()
        wizard = (
            self.env["federation.person.request.review"]
            .with_user(self.manager)
            .browse(action["res_id"])
        )
        with self.assertRaises(ValidationError):
            wizard.action_confirm()
        with self.assertRaises(AccessError):
            wizard.write({"revision": 99})
        wizard.write({"inspected": True})
        wizard.action_confirm()
        self.assertEqual(request.verified_revision, request.document_revision)
        self.assertEqual(request.verified_by_id, self.manager)
        self.assertTrue(request.verified_on)
        request.write({"review_note": "New evidence required"})
        request.action_return()
        self.assertFalse(request.verified_by_id)
        self.assertEqual(request.verified_revision, 0)
