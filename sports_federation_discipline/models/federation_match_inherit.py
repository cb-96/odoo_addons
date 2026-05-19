from odoo import fields, models


class FederationMatch(models.Model):
    _inherit = "federation.match"

    incident_ids = fields.One2many(
        "federation.match.incident",
        "match_id",
        string="Incidents",
    )
    incident_count = fields.Integer(
        compute="_compute_incident_count",
        string="Incident Count",
    )

    def _compute_incident_count(self):
        """Compute incident count."""
        for record in self:
            record.incident_count = len(record.incident_ids)

    def action_view_incidents(self):
        """Execute the view incidents action."""
        self.ensure_one()
        action = self.env.ref(
            "sports_federation_discipline.action_federation_incident"
        ).read()[0]
        action["domain"] = [("match_id", "=", self.id)]
        action["context"] = {"default_match_id": self.id}
        return action
