from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionFormatSetupWizard(models.TransientModel):
    _name = "federation.competition.format.setup.wizard"
    _description = "Choose Competition Format"

    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, readonly=True
    )
    division_id = fields.Many2one(
        "federation.tournament",
        required=True,
        domain="[('edition_id', '=', edition_id)]",
    )
    participant_set_id = fields.Many2one(
        "federation.participant.set", required=True, readonly=True
    )
    team_count = fields.Integer(compute="_compute_team_count")
    format_type = fields.Selection(
        [
            ("single_round_robin", "League - play each team once"),
            ("double_round_robin", "Home & away league"),
            ("knockout", "Knockout cup"),
        ],
        required=True,
        default="single_round_robin",
        string="Format",
    )

    preview_match_count = fields.Integer(compute="_compute_format_preview", string="Total matches")
    preview_matches_per_team = fields.Integer(compute="_compute_format_preview", string="Matches per team (league)")
    preview_byes = fields.Integer(compute="_compute_format_preview", string="First-round byes")
    preview_confirmed = fields.Boolean(string="I have reviewed this format")

    @api.depends("participant_set_id.line_ids", "format_type")
    def _compute_format_preview(self):
        for wizard in self:
            n = len(wizard.participant_set_id.line_ids)
            multiplier = 2 if wizard.format_type == "double_round_robin" else 1
            wizard.preview_match_count = max(n - 1, 0) if wizard.format_type == "knockout" else n * max(n - 1, 0) // 2 * multiplier
            wizard.preview_matches_per_team = 0 if wizard.format_type == "knockout" else max(n - 1, 0) * multiplier
            wizard.preview_byes = (1 << (n - 1).bit_length()) - n if n > 1 and wizard.format_type == "knockout" else 0

    @api.onchange("format_type", "division_id")
    def _reset_preview_confirmation(self):
        self.preview_confirmed = False

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        edition = self.env["federation.competition.edition"].browse(
            values.get("edition_id") or self.env.context.get("default_edition_id")
        ).exists()
        division = self.env["federation.tournament"].browse(
            values.get("division_id") or self.env.context.get("default_division_id")
        ).exists()
        if edition and not division:
            division = edition.tournament_ids.sorted(
                lambda item: (item.name or "", item.id)
            )[:1]
        if edition:
            values["edition_id"] = edition.id
            values["format_type"] = edition.setup_default_format_type
        if division:
            values["division_id"] = division.id
            participant_set = self._latest_participant_set(edition, division)
            values["participant_set_id"] = participant_set.id
        return values

    @api.model
    def _latest_participant_set(self, edition, division):
        if not edition or not division or division.edition_id != edition:
            raise ValidationError(_("Select a division from this competition."))
        participant_set = self.env["federation.participant.set"].search(
            [
                ("edition_id", "=", edition.id),
                ("division_id", "=", division.id),
                ("state", "=", "finalized"),
            ],
            order="id desc",
            limit=1,
        )
        if not participant_set:
            raise ValidationError(_("Select and save the division teams first."))
        return participant_set

    @api.depends("participant_set_id", "participant_set_id.line_ids")
    def _compute_team_count(self):
        for wizard in self:
            wizard.team_count = len(wizard.participant_set_id.line_ids)

    @api.onchange("division_id")
    def _onchange_division_id(self):
        if self.division_id:
            self.participant_set_id = self._latest_participant_set(
                self.edition_id, self.division_id
            )

    def action_apply(self):
        self.ensure_one()
        if not self.preview_confirmed:
            raise ValidationError(_("Review the format preview before confirming."))
        participant_set = self._latest_participant_set(
            self.edition_id, self.division_id
        )
        if participant_set != self.participant_set_id:
            raise ValidationError(_("The participating teams changed. Reopen and review the format."))
        existing = self.env["federation.competition.structure"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("division_id", "=", self.division_id.id),
                ("participant_set_id", "=", participant_set.id),
                ("format_type", "=", self.format_type),
                ("state", "in", ("draft", "generated", "frozen")),
            ],
            order="version desc,id desc",
            limit=1,
        )
        structure = existing
        if not structure:
            latest = self.env["federation.competition.structure"].search(
                [("division_id", "=", self.division_id.id)],
                order="version desc,id desc",
                limit=1,
            )
            structure = self.env["federation.competition.structure"].create(
                {
                    "name": _(
                        "%(division)s format", division=self.division_id.display_name
                    ),
                    "edition_id": self.edition_id.id,
                    "division_id": self.division_id.id,
                    "participant_set_id": participant_set.id,
                    "version": (latest.version + 1) if latest else 1,
                    "format_type": self.format_type,
                }
            )
        if structure.state == "draft":
            structure.action_generate()
        if structure.state == "generated":
            structure.action_freeze()
        if hasattr(self.edition_id, "action_open_competition_planner"):
            return self.edition_id.action_open_competition_planner()
        return structure.get_formview_action()
