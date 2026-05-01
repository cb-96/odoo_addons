from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationTournamentStage(models.Model):
    _name = "federation.tournament.stage"
    _description = "Tournament Stage"
    _order = "sequence, id"

    name = fields.Char(string="Stage Name", required=True)
    tournament_id = fields.Many2one(
        "federation.tournament", string="Tournament", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(string="Sequence", default=10)
    stage_type = fields.Selection(
        [
            ("group", "Group Phase"),
            ("knockout", "Knockout"),
            ("final", "Final"),
            ("placement", "Placement"),
        ],
        string="Stage Type",
        default="group",
        required=True,
    )
    date_start = fields.Date(string="Start Date")
    date_end = fields.Date(string="End Date")
    notes = fields.Text(string="Notes")

    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        help="Optional stage-specific rule set. Overrides the tournament-level rule set when set.",
    )

    group_ids = fields.One2many(
        "federation.tournament.group", "stage_id", string="Groups"
    )
    round_ids = fields.One2many(
        "federation.tournament.round", "stage_id", string="Rounds"
    )
    match_ids = fields.One2many("federation.match", "stage_id", string="Matches")

    group_count = fields.Integer(
        string="Group Count", compute="_compute_counts", store=True
    )
    round_count = fields.Integer(
        string="Round Count", compute="_compute_counts", store=True
    )
    match_count = fields.Integer(
        string="Match Count", compute="_compute_counts", store=True
    )

    @api.depends("group_ids", "round_ids", "match_ids")
    def _compute_counts(self):
        """Compute counts."""
        for rec in self:
            rec.group_count = len(rec.group_ids)
            rec.round_count = len(rec.round_ids)
            rec.match_count = len(rec.match_ids)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError("End date must be on or after start date.")

    def action_view_groups(self):
        """Execute the view groups action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_group_action"
        )
        action["domain"] = [("stage_id", "=", self.id)]
        return action

    def action_view_rounds(self):
        """Execute the view rounds action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_round_action"
        )
        action["domain"] = [("stage_id", "=", self.id)]
        return action

    def action_view_matches(self):
        """Execute the view matches action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_match_action"
        )
        action["domain"] = [("stage_id", "=", self.id)]
        return action
