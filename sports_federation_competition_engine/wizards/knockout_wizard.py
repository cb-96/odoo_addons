from odoo import api, fields, models, _
from odoo.exceptions import UserError


class KnockoutWizard(models.TransientModel):
    _name = "federation.knockout.wizard"
    _description = "Generate Knockout Bracket"

    tournament_id = fields.Many2one("federation.tournament", required=True)
    stage_id = fields.Many2one(
        "federation.tournament.stage",
        required=True,
        domain="[('tournament_id', '=', tournament_id)]",
    )
    participant_source = fields.Selection(
        [
            ("manual", "Manual List"),
            ("tournament", "Tournament Participants"),
            ("stage", "From Previous Stage"),
        ],
        default="tournament",
        required=True,
    )
    participant_ids = fields.Many2many(
        "federation.tournament.participant",
        relation="fed_ko_wiz_participant_rel",
        domain="[('tournament_id', '=', tournament_id)]",
    )
    source_stage_id = fields.Many2one(
        "federation.tournament.stage", domain="[('tournament_id', '=', tournament_id)]"
    )
    seeding = fields.Selection(
        [
            ("seed", "By Seed"),
            ("random", "Random"),
            ("manual", "Manual Order"),
        ],
        default="seed",
        required=True,
    )
    bracket_size = fields.Selection(
        [
            ("natural", "Natural Size"),
            ("power_of_two", "Next Power of 2"),
        ],
        default="power_of_two",
        required=True,
    )
    bracket_type = fields.Selection(
        [
            ("winners", "Winners"),
            ("losers", "Losers"),
            ("consolation", "Consolation"),
            ("placement_3rd", "3rd Place"),
            ("placement_5th", "5th Place"),
            ("placement_7th", "7th Place"),
        ],
        string="Bracket Type",
        default="winners",
        required=True,
    )
    start_datetime = fields.Datetime()
    interval_hours = fields.Integer(default=2)
    venue = fields.Char()
    overwrite = fields.Boolean()
    summary = fields.Text(compute="_compute_summary")

    @api.depends(
        "tournament_id",
        "stage_id",
        "participant_source",
        "participant_ids",
        "source_stage_id",
        "bracket_size",
    )
    def _compute_summary(self):
        """Compute summary."""
        import math

        for wiz in self:
            parts = wiz._get_participants()
            n = len(parts)
            if n < 2:
                wiz.summary = "Need at least 2 participants."
                continue
            if wiz.bracket_size == "power_of_two":
                bracket = 2 ** math.ceil(math.log2(n))
                byes = bracket - n
            else:
                bracket = n
                byes = 0
            wiz.summary = f"{n} participants, bracket {bracket}, {byes} byes, {bracket // 2} matches."

    def _get_participants(self):
        """Return participants."""
        self.ensure_one()
        if self.participant_source == "manual":
            return self.participant_ids
        elif self.participant_source == "tournament":
            return self.env["federation.tournament.participant"].search(
                [
                    ("tournament_id", "=", self.tournament_id.id),
                    ("state", "=", "confirmed"),
                ]
            )
        elif self.participant_source == "stage" and self.source_stage_id:
            return self.env["federation.tournament.participant"].search(
                [
                    ("tournament_id", "=", self.tournament_id.id),
                    ("stage_id", "=", self.source_stage_id.id),
                    ("state", "=", "confirmed"),
                ]
            )
        return self.env["federation.tournament.participant"]

    def action_generate(self):
        """Execute the generate action."""
        self.ensure_one()
        participants = self._get_participants()
        self._validate_generation_request(participants)
        options = {
            "seeding": self.seeding,
            "bracket_size": self.bracket_size,
            "bracket_type": self.bracket_type,
            "start_datetime": self.start_datetime,
            "interval_hours": self.interval_hours,
            "venue": self.venue or "",
            "overwrite": self.overwrite,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament_id, self.stage_id, participants, options
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bracket Generated"),
                "message": _("%d matches created.") % len(matches),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _validate_generation_request(self, participants):
        """Validate generation request."""
        if self.tournament_id.state not in ("open", "in_progress"):
            raise UserError(_("Tournament must be Open or In Progress."))

        if not self.tournament_id._get_effective_rule_set():
            raise UserError(
                _("Assign a rule set before generating a knockout bracket.")
            )

        if self.stage_id.tournament_id != self.tournament_id:
            raise UserError(
                _("The selected stage must belong to the selected tournament.")
            )

        if self.participant_source == "stage" and not self.source_stage_id:
            raise UserError(
                _("Select a source stage when using previous-stage participants.")
            )

        if len(participants) < 2:
            raise UserError(_("At least 2 confirmed participants required."))
