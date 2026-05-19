from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchIncident(models.Model):
    _name = "federation.match.incident"
    _description = "Match Incident"
    _order = "date_reported desc, id desc"

    name = fields.Char(required=True)
    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        ondelete="set null",
        index=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        ondelete="set null",
        index=True,
    )
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        ondelete="set null",
        index=True,
    )
    referee_id = fields.Many2one(
        "federation.referee",
        string="Referee",
        ondelete="set null",
        index=True,
    )
    incident_type = fields.Selection(
        [
            ("warning", "Warning"),
            ("yellow_card", "Yellow Card"),
            ("red_card", "Red Card"),
            ("misconduct", "Misconduct"),
            ("violence", "Violence"),
            ("admin_issue", "Administrative Issue"),
            ("other", "Other"),
        ],
        required=True,
    )
    minute_text = fields.Char(string="Minute")
    description = fields.Text(required=True)
    case_id = fields.Many2one(
        "federation.disciplinary.case",
        string="Case",
        ondelete="set null",
        index=True,
    )
    date_reported = fields.Date(
        string="Date Reported",
        default=fields.Date.context_today,
    )
    reported_by_user_id = fields.Many2one(
        "res.users",
        string="Reported By",
        default=lambda self: self.env.user,
    )
    status = fields.Selection(
        [
            ("new", "New"),
            ("attached", "Attached to Case"),
            ("closed", "Closed"),
        ],
        default="new",
        required=True,
    )

    @api.constrains("match_id", "player_id", "club_id", "referee_id")
    def _check_subject_reference(self):
        """Validate subject reference."""
        for record in self:
            if not any(
                [
                    record.match_id,
                    record.player_id,
                    record.club_id,
                    record.referee_id,
                ]
            ):
                raise ValidationError(
                    "At least one of Match, Player, Club, or Referee must be set."
                )
