from io import BytesIO

from werkzeug.datastructures import FileStorage

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestParentalApprovalPortal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_group = cls.env.ref("sports_federation_portal.group_federation_portal_club")
        cls.role_type = cls.env.ref("sports_federation_portal.role_type_competition_contact")
        cls.club = cls.env["federation.club"].create({"name": "Consent Club", "code": "CONS"})
        cls.other_club = cls.env["federation.club"].create({"name": "Foreign Club", "code": "FORE"})
        cls.user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Consent Representative", "login": "consent.rep@example.com",
            "group_ids": [(6, 0, [cls.portal_group.id])],
        })
        cls.env["federation.club.representative"].create({
            "club_id": cls.club.id, "partner_id": cls.user.partner_id.id,
            "user_id": cls.user.id, "role_type_id": cls.role_type.id,
        })
        cls.player = cls.env["federation.player"].create({"first_name": "Minor", "last_name": "Player", "club_id": cls.club.id})
        cls.other_player = cls.env["federation.player"].create({"first_name": "Foreign", "last_name": "Player", "club_id": cls.other_club.id})

    def _upload(self):
        return FileStorage(stream=BytesIO(b"%PDF-1.4 signed consent"), filename="consent.pdf", content_type="application/pdf")

    def test_representative_uploads_owned_player_approval_as_draft(self):
        approval = self.env["federation.player.parental.approval"]._portal_create_parental_approval(
            self.player, {"guardian_name": "Parent", "approval_date": "2026-10-11", "valid_until": "2027-10-11"}, self._upload(), user=self.user,
        )
        self.assertEqual(approval.player_id, self.player)
        self.assertEqual(approval.state, "draft")
        self.assertEqual(approval.create_uid, self.user)
        self.assertTrue(approval.approval_document)
        self.assertEqual(approval.submitted_by_id, self.user)
        self.assertTrue(approval.submitted_on)

    def test_representative_cannot_upload_for_foreign_player(self):
        with self.assertRaises(AccessError):
            self.env["federation.player.parental.approval"]._portal_create_parental_approval(
                self.other_player, {"guardian_name": "Parent", "approval_date": "2026-10-11"}, self._upload(), user=self.user,
            )


    def test_second_pending_upload_is_rejected(self):
        model = self.env["federation.player.parental.approval"]
        values = {"guardian_name": "Parent", "approval_date": "2026-10-11"}
        model._portal_create_parental_approval(self.player, values, self._upload(), user=self.user)
        with self.assertRaises(ValidationError):
            model._portal_create_parental_approval(self.player, values, self._upload(), user=self.user)

    def test_replacement_requires_review_note(self):
        approval = self.env["federation.player.parental.approval"].create({
            "player_id": self.player.id,
            "guardian_name": "Parent",
            "approval_date": "2026-10-11",
            "approval_document": b"c2lnbmVk",
        })
        with self.assertRaises(ValidationError):
            approval.action_request_replacement()
        approval.review_note = "Signature is missing."
        approval.action_request_replacement()
        self.assertEqual(approval.state, "replacement_requested")

    def test_representative_without_federation_function_cannot_be_internal(self):
        internal = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Wrong Internal Representative", "login": "wrong.internal@example.com",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(ValidationError):
            self.env["federation.club.representative"].create({
                "club_id": self.club.id, "partner_id": internal.partner_id.id,
                "user_id": internal.id, "role_type_id": self.role_type.id,
            })
