from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationSanction(models.Model):
    _name = "federation.sanction"
    _description = "Sanction"
    _order = "effective_date desc, id desc"

    name = fields.Char(required=True)
    case_id = fields.Many2one(
        "federation.disciplinary.case",
        string="Case",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sanction_type = fields.Selection(
        [
            ("warning", "Warning"),
            ("fine", "Fine"),
            ("suspension", "Suspension"),
            ("forfeit_recommendation", "Forfeit Recommendation"),
            ("other", "Other"),
        ],
        required=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        ondelete="set null",
    )
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        ondelete="set null",
    )
    referee_id = fields.Many2one(
        "federation.referee",
        string="Referee",
        ondelete="set null",
    )
    amount = fields.Monetary(string="Amount", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    effective_date = fields.Date(string="Effective Date")
    notes = fields.Text(string="Notes")

    @api.constrains("player_id", "club_id", "referee_id", "case_id")
    def _check_subject(self):
        """Validate subject."""
        for record in self:
            has_subject = any(
                [
                    record.player_id,
                    record.club_id,
                    record.referee_id,
                    record.case_id.subject_player_id,
                    record.case_id.subject_club_id,
                    record.case_id.subject_referee_id,
                ]
            )
            if not has_subject:
                raise ValidationError(
                    "Sanction must have a subject (Player, Club, or Referee) "
                    "either directly or through the linked case."
                )
