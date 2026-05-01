from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationSeason(models.Model):
    _name = "federation.season"
    _description = "Federation Season"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc"

    name = fields.Char(string="Season Name", required=True, tracking=True)
    code = fields.Char(string="Code", copy=False)
    active = fields.Boolean(default=True)
    date_start = fields.Date(string="Start Date", required=True, tracking=True)
    date_end = fields.Date(string="End Date", required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        required=True,
    )
    target_club_count = fields.Integer(string="Target Clubs", default=0)
    target_team_count = fields.Integer(string="Target Teams", default=0)
    target_tournament_count = fields.Integer(string="Target Tournaments", default=0)
    target_participant_count = fields.Integer(
        string="Target Tournament Participants", default=0
    )
    notes = fields.Text(string="Notes")

    registration_ids = fields.One2many(
        "federation.season.registration", "season_id", string="Registrations"
    )
    registration_count = fields.Integer(
        string="Registration Count", compute="_compute_registration_count", store=True
    )

    _code_unique = models.Constraint("unique (code)", "Season code must be unique.")

    @api.depends("registration_ids")
    def _compute_registration_count(self):
        """Compute registration count."""
        for rec in self:
            rec.registration_count = len(rec.registration_ids)

    def action_view_registrations(self):
        """Execute the view registrations action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_base.federation_season_registration_action"
        )
        action["domain"] = [("season_id", "=", self.id)]
        return action

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start >= rec.date_end:
                raise ValidationError("End date must be after start date.")

    @api.constrains(
        "target_club_count",
        "target_team_count",
        "target_tournament_count",
        "target_participant_count",
    )
    def _check_planning_targets(self):
        """Validate planning targets."""
        for rec in self:
            target_values = [
                rec.target_club_count,
                rec.target_team_count,
                rec.target_tournament_count,
                rec.target_participant_count,
            ]
            if any(value < 0 for value in target_values):
                raise ValidationError(
                    _("Planning target values must be zero or greater.")
                )

    def action_open(self):
        """Execute the open action."""
        invalid_seasons = self.filtered(
            lambda rec: rec.state != "draft" or not rec.active
        )
        if invalid_seasons:
            raise ValidationError(_("Only active draft seasons can be opened."))
        self.write({"state": "open"})

    def action_close(self):
        """Execute the close action."""
        invalid_seasons = self.filtered(lambda rec: rec.state != "open")
        if invalid_seasons:
            raise ValidationError(_("Only open seasons can be closed."))
        self.write({"state": "closed"})

    def action_cancel(self):
        """Execute the cancel action."""
        invalid_seasons = self.filtered(lambda rec: rec.state not in ("draft", "open"))
        if invalid_seasons:
            raise ValidationError(_("Only draft or open seasons can be cancelled."))
        self.write({"state": "cancelled"})

    def action_draft(self):
        """Execute the draft action."""
        invalid_seasons = self.filtered(lambda rec: rec.state != "cancelled")
        if invalid_seasons:
            raise ValidationError(_("Only cancelled seasons can be reset to draft."))
        self.write({"state": "draft"})

    def action_archive(self):
        """Execute the archive action."""
        active_seasons = self.filtered(lambda rec: rec.state == "open")
        if active_seasons:
            raise ValidationError(
                _("Close or cancel an open season before archiving it.")
            )
        self.write({"active": False})
        return True

    def action_restore(self):
        """Execute the restore action."""
        self.write({"active": True})
        return True
