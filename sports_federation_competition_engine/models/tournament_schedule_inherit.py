from odoo import models


class FederationTournamentStageInherit(models.Model):
    _inherit = "federation.tournament.stage"

    def action_open_round_date_wizard(self):
        """Open the kickoff date wizard pre-filled with this stage."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Set Kickoff Dates",
            "res_model": "federation.round.date.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_stage_id": self.id},
        }


class FederationTournamentRoundInherit(models.Model):
    _inherit = "federation.tournament.round"

    def action_open_round_date_wizard(self):
        """Open the kickoff date wizard pre-filled with this round."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Set Kickoff Dates",
            "res_model": "federation.round.date.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_stage_id": self.stage_id.id,
                "default_round_id": self.id,
            },
        }
