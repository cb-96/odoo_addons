from odoo import api, fields, models
from odoo.addons.sports_federation_governance.workflow_states import (
    OVERRIDE_REQUEST_STATE_SELECTION,
)


class FederationOverrideOutcome(models.Model):
    _name = "federation.override.outcome"
    _description = "Federation Override Outcome"
    _order = "outcome_on desc, id desc"

    OUTCOME_SELECTION = [
        ("implemented", "Implemented"),
        ("effective", "Effective"),
        ("partial", "Partially Effective"),
        ("ineffective", "Ineffective"),
        ("reversed", "Reversed"),
    ]
    REQUEST_STATE_SELECTION = OVERRIDE_REQUEST_STATE_SELECTION

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    request_id = fields.Many2one(
        "federation.override.request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    outcome = fields.Selection(selection=OUTCOME_SELECTION, required=True, index=True)
    outcome_on = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    recorded_by_id = fields.Many2one(
        "res.users",
        string="Recorded By",
        default=lambda self: self.env.user,
        required=True,
    )
    request_type = fields.Selection(
        related="request_id.request_type",
        string="Request Type",
        store=True,
        readonly=True,
    )
    target_model = fields.Char(string="Target Model", readonly=True)
    target_res_id = fields.Integer(string="Target Record ID", readonly=True)
    request_state = fields.Selection(
        selection=REQUEST_STATE_SELECTION,
        string="Request State",
        readonly=True,
    )
    note = fields.Text(string="Outcome Note")

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        prepared_vals_list = []
        for vals in vals_list:
            prepared_vals = dict(vals)
            request = self.env["federation.override.request"].browse(
                prepared_vals.get("request_id")
            )
            if request:
                prepared_vals.setdefault("request_state", request.state)
                prepared_vals.setdefault("target_model", request.target_model)
                prepared_vals.setdefault("target_res_id", request.target_res_id)
            prepared_vals_list.append(prepared_vals)
        return super().create(prepared_vals_list)

    @api.depends("request_id", "outcome", "outcome_on")
    def _compute_name(self):
        """Compute name."""
        labels = dict(self._fields["outcome"].selection)
        for record in self:
            outcome_label = labels.get(record.outcome, record.outcome or "Outcome")
            request_label = record.request_id.display_name or "Override Request"
            record.name = (
                f"{request_label} - {outcome_label} - {record.outcome_on}"
                if record.outcome_on
                else f"{request_label} - {outcome_label}"
            )
