import base64

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationPlayerParentalApprovalPortal(models.Model):
    _inherit = "federation.player.parental.approval"

    @api.model
    def _portal_create_parental_approval(self, player, values, upload, user=None):
        """Create a club-scoped draft from a validated portal upload.

        Verification deliberately remains a federation backend action.  The
        portal actor can only create immutable-at-review draft evidence for a
        player in a currently represented club.
        """
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        represented_clubs = privilege.elevate(
            self.env["federation.club.representative"], user=user
        )._get_clubs_for_user(user=user)
        player = privilege.portal_assert_in_domain(
            player,
            [("club_id", "in", represented_clubs.ids)],
            _("You can only upload parental approval for players in your club."),
            user=user,
        )
        player.ensure_one()
        if not upload or not getattr(upload, "filename", False):
            raise ValidationError(_("Select a signed approval document to upload."))

        payload = upload.read()
        checked = self.env["federation.attachment.policy"].validate_upload(
            "portal_document",
            upload.filename,
            payload,
            mimetype=getattr(upload, "content_type", False),
        )
        guardian_name = (values.get("guardian_name") or "").strip()
        if not guardian_name:
            raise ValidationError(_("Parent or guardian name is required."))
        approval_date = fields.Date.to_date(values.get("approval_date"))
        valid_until = fields.Date.to_date(values.get("valid_until"))
        if not approval_date:
            raise ValidationError(_("Approval date is required."))

        approval_values = {
            "player_id": player.id,
            "guardian_name": guardian_name,
            "guardian_email": (values.get("guardian_email") or "").strip() or False,
            "approval_date": approval_date,
            "valid_until": valid_until or False,
            "approval_document": base64.b64encode(checked["payload"]),
            "approval_document_filename": checked["filename"],
            "notes": (values.get("notes") or "").strip() or False,
            "state": "draft",
        }
        return privilege.portal_create(self, approval_values, user=user)
