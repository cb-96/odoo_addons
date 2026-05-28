from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class FederationReferee(models.Model):
    _inherit = "federation.referee"

    user_id = fields.Many2one(
        "res.users",
        string="Portal User",
        ondelete="set null",
        index=True,
        help="Portal user allowed to review and respond to this referee profile's assignments.",
    )

    _user_unique = models.Constraint(
        "UNIQUE(user_id)",
        "A portal user can only be linked to one referee profile.",
    )

    @api.model
    def _portal_get_for_user(self, user=None):
        """Handle the portal-specific get for user flow."""
        user = user or self.env.user
        return self.with_user(user).sudo().search([("user_id", "=", user.id)], limit=1)

    def _portal_assert_access(self, user=None):
        """Handle the portal-specific assert access flow."""
        user = user or self.env.user
        for record in self:
            if record.user_id != user:
                raise AccessError(_("You can only access your own referee profile."))
        return True
