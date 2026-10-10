from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionTeamSelectionWizard(models.TransientModel):
    _name = "federation.competition.team.selection.wizard"
    _description = "Select Competition Teams"

    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, readonly=True
    )
    division_id = fields.Many2one(
        "federation.tournament",
        required=True,
        domain="[('edition_id', '=', edition_id)]",
    )
    window_id = fields.Many2one(
        "federation.registration.window", readonly=True
    )
    eligible_team_ids = fields.Many2many(
        "federation.team", compute="_compute_eligible_team_ids"
    )
    team_ids = fields.Many2many(
        "federation.team",
        "federation_team_selection_wizard_team_rel",
        "wizard_id",
        "team_id",
        string="Teams",
        domain="[('id', 'in', eligible_team_ids)]",
        required=True,
    )

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
            division = edition.tournament_ids.sorted(lambda item: (item.name or "", item.id))[:1]
        if edition:
            values["edition_id"] = edition.id
        if division:
            values["division_id"] = division.id
            window = self._window_for_division(edition, division, create=False)
            values["window_id"] = window.id if window else False
            if window and window.participant_set_id:
                values["team_ids"] = [
                    fields.Command.set(window.participant_set_id.line_ids.mapped("team_id").ids)
                ]
            elif window and window.entry_ids:
                values["team_ids"] = [
                    fields.Command.set(
                        window.entry_ids.filtered(
                            lambda entry: entry.state != "withdrawn"
                        ).mapped("team_id").ids
                    )
                ]
        return values

    @api.model
    def _window_for_division(self, edition, division, *, create=True):
        if not edition or not division or division.edition_id != edition:
            raise ValidationError(_("Select a division from this competition."))
        window = self.env["federation.registration.window"].search(
            [("edition_id", "=", edition.id), ("division_id", "=", division.id)],
            order="id desc",
            limit=1,
        )
        return window or (create and self.env["federation.registration.window"].create(
            {
                "name": _("Team selection - %(division)s", division=division.display_name),
                "edition_id": edition.id,
                "division_id": division.id,
            }
        ))

    @api.depends("division_id", "division_id.category", "division_id.gender")
    def _compute_eligible_team_ids(self):
        Team = self.env["federation.team"]
        for wizard in self:
            wizard.eligible_team_ids = (
                wizard.division_id.search_eligible_teams(
                    extra_domain=[("active", "=", True)]
                )
                if wizard.division_id
                else Team
            )

    @api.onchange("division_id")
    def _onchange_division_id(self):
        if not self.division_id:
            self.window_id = False
            self.team_ids = False
            return
        self.window_id = self._window_for_division(
            self.edition_id, self.division_id, create=False
        )
        self.team_ids = (
            self.window_id.participant_set_id.line_ids.mapped("team_id")
            or self.window_id.entry_ids.filtered(
                lambda entry: entry.state != "withdrawn"
            ).mapped("team_id")
            if self.window_id
            else self.env["federation.team"]
        )

    def action_apply(self):
        self.ensure_one()
        window = self.window_id or self._window_for_division(
            self.edition_id, self.division_id
        )
        window.materialize_direct_team_selection(self.team_ids)
        if hasattr(self.edition_id, "action_open_competition_planner"):
            return self.edition_id.action_open_competition_planner()
        return window.get_formview_action()