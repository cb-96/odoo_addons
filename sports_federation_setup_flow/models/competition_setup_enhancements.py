from dateutil.relativedelta import relativedelta

from odoo import _, fields, models


class FederationCompetitionEditionSetupEnhancements(models.Model):
    _inherit = "federation.competition.edition"

    setup_preset = fields.Selection(
        [
            ("league", "Season League"),
            ("tournament_day", "One-Day Tournament"),
            ("cup", "Knockout Cup"),
            ("custom", "Custom"),
        ],
        default="league",
        required=True,
        string="Competition Preset",
        help="Remembers the operator defaults used by the resumable workspace.",
    )
    setup_default_format_type = fields.Selection(
        [
            ("single_round_robin", "League"),
            ("double_round_robin", "Home & Away League"),
            ("knockout", "Knockout Cup"),
        ],
        default="single_round_robin",
        required=True,
        string="Default Format",
    )
    setup_default_venue_id = fields.Many2one("federation.venue", string="Default Venue")
    setup_default_start_hour = fields.Float(default=9.0, required=True)
    setup_default_end_hour = fields.Float(default=18.0, required=True)
    setup_default_slot_duration_minutes = fields.Integer(default=40, required=True)

    def action_open_clone_setup(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Copy Competition Setup"),
            "res_model": "federation.competition.clone.setup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": dict(
                self.env.context,
                default_source_edition_id=self.id,
                default_name=_("Copy of %s") % self.name,
                default_date_start=(
                    self.date_start + relativedelta(years=1)
                    if self.date_start
                    else False
                ),
                default_date_end=(
                    self.date_end + relativedelta(years=1) if self.date_end else False
                ),
            ),
        }
