from dateutil.relativedelta import relativedelta

from odoo import _, fields, models


class FederationCompetitionEditionSetupEnhancements(models.Model):
    _inherit = "federation.competition.edition"

    setup_default_venue_id = fields.Many2one("federation.venue", string="Default Venue")

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
