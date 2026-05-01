from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionEdition(models.Model):
    _name = "federation.competition.edition"
    _description = "Competition Edition"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, name"

    name = fields.Char(
        string="Edition Name",
        required=True,
        tracking=True,
        help="e.g. 'Premier League 2025-2026', 'Youth Cup Spring 2026'",
    )
    competition_id = fields.Many2one(
        "federation.competition",
        string="Competition Template",
        required=True,
        tracking=True,
        ondelete="restrict",
        help="The competition template this edition is based on.",
    )
    season_id = fields.Many2one(
        "federation.season",
        string="Season",
        required=True,
        tracking=True,
        ondelete="restrict",
    )
    competition_type = fields.Selection(
        related="competition_id.competition_type",
        store=True,
        readonly=True,
    )
    date_start = fields.Date(string="Start Date", tracking=True)
    date_end = fields.Date(string="End Date", tracking=True)
    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        tracking=True,
        ondelete="set null",
        help="Rule set for this edition. Defaults to the competition template's rule set.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("in_progress", "In Progress"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    tournament_ids = fields.One2many(
        "federation.tournament",
        "edition_id",
        string="Divisions / Tournaments",
    )
    tournament_count = fields.Integer(
        string="Division Count",
        compute="_compute_tournament_count",
        store=False,
    )
    notes = fields.Text(string="Notes")
    active = fields.Boolean(default=True)

    _edition_unique = models.Constraint(
        "unique (competition_id, season_id)",
        "An edition already exists for this competition and season.",
    )

    @api.depends("tournament_ids")
    def _compute_tournament_count(self):
        """Compute tournament count."""
        for rec in self:
            rec.tournament_count = len(rec.tournament_ids)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError("End date must be on or after start date.")

    @api.onchange("competition_id")
    def _onchange_competition_id(self):
        """Handle onchange competition ID."""
        if (
            self.competition_id
            and self.competition_id.rule_set_id
            and not self.rule_set_id
        ):
            self.rule_set_id = self.competition_id.rule_set_id

    def action_open(self):
        """Execute the open action."""
        for rec in self:
            rec.state = "open"

    def action_start(self):
        """Execute the start action."""
        for rec in self:
            rec.state = "in_progress"

    def action_close(self):
        """Execute the close action."""
        for rec in self:
            rec.state = "closed"

    def action_cancel(self):
        """Execute the cancel action."""
        for rec in self:
            rec.state = "cancelled"

    def action_draft(self):
        """Execute the draft action."""
        for rec in self:
            rec.state = "draft"

    def action_view_tournaments(self):
        """Execute the view tournaments action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_action"
        )
        action["domain"] = [("edition_id", "=", self.id)]
        return action
