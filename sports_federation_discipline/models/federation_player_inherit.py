from odoo import fields, models


class FederationPlayer(models.Model):
    _inherit = "federation.player"

    suspension_ids = fields.One2many(
        "federation.suspension",
        "player_id",
        string="Suspensions",
    )
    suspension_count = fields.Integer(
        compute="_compute_suspension_count",
        string="Suspension Count",
    )

    def _compute_suspension_count(self):
        """Compute suspension count."""
        for record in self:
            record.suspension_count = len(record.suspension_ids)

    def action_view_suspensions(self):
        """Execute the view suspensions action."""
        self.ensure_one()
        action = self.env.ref(
            "sports_federation_discipline.action_federation_suspension"
        ).read()[0]
        action["domain"] = [("player_id", "=", self.id)]
        action["context"] = {"default_player_id": self.id}
        return action
