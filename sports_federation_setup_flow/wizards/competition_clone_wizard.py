from datetime import timedelta

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
    copy_gameday_pattern = fields.Boolean(
        default=True,
        string="Copy game days",
        help="Same weekdays, venues, courts and hours, moved to the new season. "
        "Each day keeps its divisions.",
    )
    copy_formats = fields.Boolean(
        default=True,
        string="Reuse formats",
        help="Each division starts with last season's format filled in once its "
        "teams are known. Nothing is generated until you confirm it.",
    )
    copy_responsibilities = fields.Boolean(default=False)

    @api.onchange("source_edition_id")
    def _onchange_source_edition_id(self):
        source = self.source_edition_id
        if not source:
            return
        self.name = _("Copy of %s") % source.name
        self.date_start = (
            source.date_start + relativedelta(years=1) if source.date_start else False
        )
        self.date_end = (
            source.date_end + relativedelta(years=1) if source.date_end else False
        )

    def action_copy_setup(self):
        self.ensure_one()
        source = self.source_edition_id
        if self.season_id == source.season_id:
            raise ValidationError(
                _("Select a different season for the copied competition.")
            )
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
        source_divisions = source.tournament_ids.sorted("id")
        division_map = {}
        for division, values in zip(
            source_divisions,
            source_divisions.copy_data(
                {
                    "edition_id": edition.id,
                    "season_id": self.season_id.id,
                    "state": "draft",
                }
            ),
        ):
            copied = self.env["federation.tournament"].create(values)
            division_map[division.id] = copied
            if self.copy_formats:
                structure = self._reusable_structure(division)
                if structure and "format_source_structure_id" in copied._fields:
                    copied.format_source_structure_id = structure.id
        if self.copy_responsibilities:
            for assignment in source.role_assignment_ids:
                assignment.copy({"edition_id": edition.id})
        if self.copy_gameday_pattern and source.date_start:
            # Move by whole weeks so a Saturday stays a Saturday.
            weeks = round((self.date_start - source.date_start).days / 7)
            for day in self.env["federation.matchday"].search(
                [("edition_id", "=", source.id), ("state", "!=", "cancelled")],
                order="date,id",
            ):
                values = {
                    "edition_id": edition.id,
                    "date": day.date + timedelta(weeks=weeks),
                    "state": "draft",
                }
                if "division_ids" in day._fields:
                    values["division_ids"] = [
                        fields.Command.set(
                            [
                                division_map[division.id].id
                                for division in day.division_ids
                                if division.id in division_map
                            ]
                        )
                    ]
                day.copy(values)
        return edition.get_formview_action()

    @api.model
    def _reusable_structure(self, division):
        """Latest generated format of a division, if any."""
        return self.env["federation.competition.structure"].search(
            [
                ("division_id", "=", division.id),
                ("state", "in", ("generated", "frozen")),
            ],
            order="version desc,id desc",
            limit=1,
        )
