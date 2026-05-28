from odoo import api, fields, models


class ResPartner(models.Model):
    """Extend res.partner with club representative links."""

    _inherit = "res.partner"

    federation_representative_ids = fields.One2many(
        "federation.club.representative",
        "partner_id",
        string="Club Representative Roles",
        help="Club representative records linked to this partner.",
    )
    federation_representative_count = fields.Integer(
        string="Representative Role Count",
        compute="_compute_federation_representative_count",
        store=True,
    )

    @api.depends("federation_representative_ids")
    def _compute_federation_representative_count(self):
        """Compute federation representative count."""
        for rec in self:
            rec.federation_representative_count = len(rec.federation_representative_ids)

    def action_view_federation_representatives(self):
        """Open the representative roles list for this partner."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Club Representative Roles",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }
