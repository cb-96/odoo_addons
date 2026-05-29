from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError


class FederationRoundDateWizard(models.TransientModel):
    _name = "federation.round.date.wizard"
    _description = "Set Kickoff Dates for a Round"

    stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Stage",
        required=True,
    )
    round_id = fields.Many2one(
        "federation.tournament.round",
        string="Round",
        required=True,
        domain="[('stage_id', '=', stage_id)]",
    )
    date_scheduled = fields.Datetime(
        string="Kickoff Date / Time",
        required=True,
    )

    @api.onchange("stage_id")
    def _onchange_stage_id(self):
        """Clear round selection when stage changes."""
        self.round_id = False

    @api.constrains("date_scheduled", "stage_id")
    def _check_date_within_stage(self):
        """Validate that date_scheduled falls within the stage's date window."""
        for wiz in self:
            stage = wiz.stage_id
            if not stage or not wiz.date_scheduled:
                continue
            date_part = wiz.date_scheduled.date()
            if stage.date_start and date_part < stage.date_start:
                raise ValidationError(
                    f"Kickoff date {date_part} is before the stage window "
                    f"start ({stage.date_start})."
                )
            if stage.date_end and date_part > stage.date_end:
                raise ValidationError(
                    f"Kickoff date {date_part} is after the stage window "
                    f"end ({stage.date_end})."
                )

    def action_apply(self):
        """Set date_scheduled on all matches in the selected round."""
        self.ensure_one()
        matches = self.env["federation.match"].search(
            [("round_id", "=", self.round_id.id)]
        )
        if not matches:
            raise UserError(f"No matches found in round '{self.round_id.name}'.")
        matches.write({"date_scheduled": self.date_scheduled})
        return {"type": "ir.actions.act_window_close"}
