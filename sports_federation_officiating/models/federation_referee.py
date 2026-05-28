from odoo import api, fields, models


class FederationReferee(models.Model):
    _name = "federation.referee"
    _description = "Federation Referee"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Name", required=True, tracking=True)
    active = fields.Boolean(default=True)
    email = fields.Char(string="Email")
    phone = fields.Char(string="Phone")
    mobile = fields.Char(string="Mobile")
    certification_level = fields.Selection(
        [
            ("local", "Local"),
            ("regional", "Regional"),
            ("national", "National"),
            ("international", "International"),
        ],
        string="Certification Level",
        tracking=True,
    )
    notes = fields.Text(string="Notes")

    certification_ids = fields.One2many(
        "federation.referee.certification", "referee_id", string="Certifications"
    )
    availability_ids = fields.One2many(
        "federation.referee.availability", "referee_id", string="Availability"
    )
    match_assignment_ids = fields.One2many(
        "federation.match.referee", "referee_id", string="Match Assignments"
    )

    certification_count = fields.Integer(
        string="Certification Count", compute="_compute_counts", store=True
    )
    availability_count = fields.Integer(
        string="Availability Count", compute="_compute_counts", store=True
    )
    assignment_count = fields.Integer(
        string="Assignment Count", compute="_compute_counts", store=True
    )

    @api.depends("certification_ids", "availability_ids", "match_assignment_ids")
    def _compute_counts(self):
        """Compute counts."""
        for rec in self:
            rec.certification_count = len(rec.certification_ids)
            rec.availability_count = len(rec.availability_ids)
            rec.assignment_count = len(rec.match_assignment_ids)

    def action_view_certifications(self):
        """Execute the view certifications action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_officiating.federation_referee_certification_action"
        )
        action["domain"] = [("referee_id", "=", self.id)]
        return action

    def action_view_assignments(self):
        """Execute the view assignments action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_officiating.federation_match_referee_action"
        )
        action["domain"] = [("referee_id", "=", self.id)]
        return action

    def action_view_availability(self):
        """Execute the view availability action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_officiating.federation_referee_availability_action"
        )
        action["domain"] = [("referee_id", "=", self.id)]
        action["context"] = {"default_referee_id": self.id}
        return action
