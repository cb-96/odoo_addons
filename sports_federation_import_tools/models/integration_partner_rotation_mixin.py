from odoo import models
from odoo.exceptions import AccessError


class FederationIntegrationPartnerRotationMixin(models.AbstractModel):
    _name = "federation.integration.partner.rotation.mixin"
    _description = "Federation Integration Partner Rotation Helpers"

    def _log_token_rotation_audit(self):
        """Record manager-driven token rotations in the shared audit log."""
        audit_model = self.env.get("federation.audit.event")
        if audit_model is None:
            return False
        changed_fields = [
            "auth_token",
            "auth_token_last4",
            "token_last_rotated_on",
            "token_rotation_required",
        ]
        for partner in self:
            audit_model.log_event(
                event_family="integration_token",
                event_type="integration_token_rotated",
                description="Integration partner token rotated through the manager action.",
                target=partner,
                actor=self.env.user,
                action_name="action_rotate_token",
                changed_fields=changed_fields,
            )
        return True

    def action_rotate_token(self):
        """Rotate the partner token and expose the raw secret one time."""
        self.ensure_one()
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError("Only federation managers can rotate integration tokens.")

        raw_token = self._issue_auth_token(rotation_required=False)
        self._log_token_rotation_audit()
        wizard = self.env["federation.integration.partner.token.wizard"].create(
            {
                "partner_id": self.id,
                "issued_token": raw_token,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Partner Token",
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
