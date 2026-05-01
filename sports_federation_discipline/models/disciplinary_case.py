from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationDisciplinaryCase(models.Model):
    _name = "federation.disciplinary.case"
    _description = "Disciplinary Case"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "opened_on desc, id desc"

    name = fields.Char(required=True, tracking=True)
    reference = fields.Char(
        string="Reference",
        copy=False,
        readonly=True,
        default="New",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("under_review", "Under Review"),
            ("decided", "Decided"),
            ("appealed", "Appealed"),
            ("closed", "Closed"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    opened_on = fields.Date(
        string="Opened On",
        default=fields.Date.context_today,
    )
    decided_on = fields.Date(string="Decided On")
    closed_on = fields.Date(string="Closed On")
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Case Owner",
    )
    incident_ids = fields.One2many(
        "federation.match.incident",
        "case_id",
        string="Incidents",
    )
    sanction_ids = fields.One2many(
        "federation.sanction",
        "case_id",
        string="Sanctions",
    )
    suspension_ids = fields.One2many(
        "federation.suspension",
        "case_id",
        string="Suspensions",
    )
    subject_player_id = fields.Many2one(
        "federation.player",
        string="Subject Player",
        ondelete="set null",
    )
    subject_club_id = fields.Many2one(
        "federation.club",
        string="Subject Club",
        ondelete="set null",
    )
    subject_referee_id = fields.Many2one(
        "federation.referee",
        string="Subject Referee",
        ondelete="set null",
    )
    summary = fields.Text(string="Summary")
    notes = fields.Text(string="Notes")
    incident_count = fields.Integer(
        compute="_compute_related_counts",
        string="Incident Count",
    )
    sanction_count = fields.Integer(
        compute="_compute_related_counts",
        string="Sanction Count",
    )
    suspension_count = fields.Integer(
        compute="_compute_related_counts",
        string="Suspension Count",
    )

    @api.depends("incident_ids", "sanction_ids", "suspension_ids")
    def _compute_related_counts(self):
        """Compute related counts."""
        for record in self:
            record.incident_count = len(record.incident_ids)
            record.sanction_count = len(record.sanction_ids)
            record.suspension_count = len(record.suspension_ids)

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("federation.disciplinary.case")
                    or "New"
                )
        return super().create(vals_list)

    @api.constrains(
        "subject_player_id",
        "subject_club_id",
        "subject_referee_id",
        "incident_ids",
    )
    def _check_subject(self):
        """Validate subject."""
        for record in self:
            if not any(
                [
                    record.subject_player_id,
                    record.subject_club_id,
                    record.subject_referee_id,
                    record.incident_ids,
                ]
            ):
                raise ValidationError(
                    "At least one subject (Player, Club, Referee) "
                    "or incident must be present."
                )

    def action_submit_review(self):
        """Execute the submit review action."""
        for record in self:
            if record.state != "draft":
                raise ValidationError("Only draft cases can be submitted for review.")
            record.state = "under_review"
            for incident in record.incident_ids:
                if incident.status == "new":
                    incident.status = "attached"

    def action_reopen(self):
        """Reopen a case under review, returning it to draft for corrections."""
        for record in self:
            if record.state != "under_review":
                raise ValidationError(
                    "Only cases under review can be reopened to draft."
                )
            record.state = "draft"

    def action_decide(self):
        """Execute the decide action."""
        for record in self:
            record.state = "decided"
            record.decided_on = fields.Date.context_today(record)

    def action_mark_appealed(self):
        """Execute the mark appealed action."""
        for record in self:
            record.state = "appealed"

    def action_close(self):
        """Execute the close action."""
        for record in self:
            record.state = "closed"
            record.closed_on = fields.Date.context_today(record)
            for incident in record.incident_ids:
                if incident.status != "closed":
                    incident.status = "closed"

    def action_view_incidents(self):
        """Open the related incidents."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Incidents",
            "res_model": "federation.match.incident",
            "view_mode": "list,form",
            "domain": [("id", "in", self.incident_ids.ids)],
        }

    def action_view_sanctions(self):
        """Open the related sanctions."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Sanctions",
            "res_model": "federation.sanction",
            "view_mode": "list,form",
            "domain": [("case_id", "=", self.id)],
        }

    def action_view_suspensions(self):
        """Open the related suspensions."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Suspensions",
            "res_model": "federation.suspension",
            "view_mode": "list,form",
            "domain": [("case_id", "=", self.id)],
        }
