from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionCloneSetupWizard(models.TransientModel):
    _name = "federation.competition.clone.setup.wizard"
    _description = "Copy Competition Setup"

    source_edition_id = fields.Many2one(
        "federation.competition.edition", required=True, readonly=True
    )
    name = fields.Char(required=True)
    season_id = fields.Many2one("federation.season", required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    copy_gameday_pattern = fields.Boolean(default=True)
    copy_responsibilities = fields.Boolean(default=False)

    @api.onchange("source_edition_id")
    def _onchange_source_edition_id(self):
        source = self.source_edition_id
        if not source:
            return
        self.name = _("Copy of %s") % source.name
        self.date_start = source.date_start + relativedelta(years=1) if source.date_start else False
        self.date_end = source.date_end + relativedelta(years=1) if source.date_end else False

    def action_copy_setup(self):
        self.ensure_one()
        source = self.source_edition_id
        if self.season_id == source.season_id:
            raise ValidationError(_("Select a different season for the copied competition."))
        if self.date_end < self.date_start:
            raise ValidationError(_("The end date must not be before the start date."))
        edition = source.copy(
            {
                "name": self.name,
                "season_id": self.season_id.id,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "state": "draft",
            }
        )
        for values in source.tournament_ids.copy_data(
            {
                "edition_id": edition.id,
                "season_id": self.season_id.id,
                "state": "draft",
            }
        ):
            self.env["federation.tournament"].create(values)
        if self.copy_responsibilities:
            for assignment in source.role_assignment_ids:
                assignment.copy({"edition_id": edition.id})
        if self.copy_gameday_pattern and source.date_start:
            for day in self.env["federation.matchday"].search(
                [("edition_id", "=", source.id)], order="date,id"
            ):
                offset = day.date - source.date_start
                day.copy(
                    {
                        "edition_id": edition.id,
                        "date": self.date_start + offset,
                        "state": "draft",
                    }
                )
        return edition.get_formview_action()
