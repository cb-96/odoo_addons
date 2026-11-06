"""Teams & format for every division on one screen.

Replaces the per-division loop (open team picker, apply, return to the hub,
open the format picker, confirm, return to the hub, repeat).  The wizard reuses
the governed commands of the existing pickers, so team lists are still
materialized into approved entries and finalized participant sets, and formats
are still generated and frozen through ``federation.competition.structure``.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .format_setup_wizard import FORMAT_CHOICES

# The same guided formats as the format step. Options such as qualifiers per
# group or the split point keep their current value and are changed with
# "Format options" in the planner.
FORMAT_SELECTION = FORMAT_CHOICES


class FederationCompetitionDivisionSetupWizard(models.TransientModel):
    _name = "federation.competition.division.setup.wizard"
    _description = "Competition Teams and Format"

    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, readonly=True
    )
    line_ids = fields.One2many(
        "federation.competition.division.setup.line", "wizard_id", string="Divisions"
    )
    total_match_count = fields.Integer(
        compute="_compute_total_match_count", string="Total matches"
    )

    @api.depends("line_ids.match_count")
    def _compute_total_match_count(self):
        for wizard in self:
            wizard.total_match_count = sum(wizard.line_ids.mapped("match_count"))

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        edition = self.env["federation.competition.edition"].browse(
            values.get("edition_id") or self.env.context.get("default_edition_id")
        ).exists()
        if not edition:
            return values
        values["edition_id"] = edition.id
        if "line_ids" in field_list:
            values["line_ids"] = [
                fields.Command.create(self._line_values(edition, division))
                for division in edition.tournament_ids.sorted(
                    lambda item: (item.name or "", item.id)
                )
            ]
        return values

    @api.model
    def _line_values(self, edition, division):
        selection = self.env["federation.competition.team.selection.wizard"]
        window = selection._window_for_division(edition, division, create=False)
        window = window.sudo()
        teams = self.env["federation.team"]
        if window and window.participant_set_id:
            teams = window.participant_set_id.line_ids.mapped("team_id")
        elif window:
            teams = window.entry_ids.filtered(
                lambda entry: entry.state != "withdrawn"
            ).mapped("team_id")
        structure = self.env["federation.competition.structure"].sudo().search(
            [
                ("edition_id", "=", edition.id),
                ("division_id", "=", division.id),
                # Drafts count too: a custom format is a draft while its
                # stages are being built and must not fall back to a league.
                ("state", "in", ("draft", "generated", "frozen")),
            ],
            order="version desc,id desc",
            limit=1,
        )
        if structure:
            format_type = self.env[
                "federation.competition.format.setup.wizard"
            ]._choice_from_structure(structure)["format_type"]
        elif "format_source_structure_id" in division._fields and division.format_source_structure_id:
            # Copied from last season: start from the format it played.
            structure = division.format_source_structure_id
            format_type = self.env[
                "federation.competition.format.setup.wizard"
            ]._choice_from_structure(structure)["format_type"]
        else:
            format_type = edition.setup_default_format_type
        if format_type not in dict(FORMAT_SELECTION):
            format_type = "single_round_robin"
        return {
            "division_id": division.id,
            "name": division.name,
            "category": division.category or False,
            "gender": division.gender or False,
            "team_ids": [fields.Command.set(teams.ids)],
            "format_type": format_type,
            "pool_count": (structure.pool_count if structure else 0) or 2,
        }

    def _create_division(self, line):
        edition = self.edition_id
        preset = edition.setup_preset or "league"
        division = self.env["federation.tournament"].create(
            {
                "name": line.name,
                "category": line.category or False,
                "gender": line.gender or False,
                "edition_id": edition.id,
                "competition_id": edition.competition_id.id,
                "season_id": edition.season_id.id,
                "rule_set_id": edition.rule_set_id.id,
                "date_start": edition.date_start,
                "date_end": edition.date_end,
                "tournament_type": "single_day" if preset == "tournament_day" else "multi_day",
            }
        )
        line.division_id = division
        return division

    @api.model
    def _format_is_current(self, division, participant_set, format_type, pool_count):
        structure = self.env["federation.competition.structure"].search(
            [
                ("division_id", "=", division.id),
                ("participant_set_id", "=", participant_set.id),
                ("state", "=", "frozen"),
            ],
            order="version desc,id desc",
            limit=1,
        )
        if not structure:
            return False
        choice = self.env[
            "federation.competition.format.setup.wizard"
        ]._choice_from_structure(structure)
        if choice["format_type"] != format_type:
            return False
        if format_type == "pool_knockout":
            return structure.pool_count == pool_count
        return True

    def action_apply(self):
        self.ensure_one()
        edition = self.edition_id
        edition.check_access("read")
        if not self.line_ids:
            raise ValidationError(_("Add at least one division."))
        names = [name.strip().lower() for name in self.line_ids.mapped("name") if name]
        if len(names) != len(set(names)):
            raise ValidationError(_("Each division needs a different name."))
        selection = self.env["federation.competition.team.selection.wizard"]
        format_wizard = self.env["federation.competition.format.setup.wizard"]
        builder_actions = []
        for line in self.line_ids:
            if not (line.name or "").strip():
                raise ValidationError(_("Every division needs a name."))
            if len(line.team_ids) == 1:
                raise ValidationError(
                    _("%(division)s: select at least two teams.", division=line.name)
                )
            try:
                division = line.division_id or self._create_division(line)
                scope = {
                    "name": line.name,
                    "category": line.category or False,
                    "gender": line.gender or False,
                }
                changed = {
                    key: value for key, value in scope.items() if division[key] != value
                }
                if changed:
                    division.write(changed)
                if not line.team_ids:
                    # Saving the division without teams is allowed; the
                    # planner keeps reporting the missing team list.
                    continue
                window = selection._window_for_division(edition, division, create=True)
                participant_set = window.sudo().materialize_direct_team_selection(
                    line.team_ids
                )
                if self._format_is_current(
                    division, participant_set, line.format_type, line.pool_count
                ):
                    continue
                if line.format_type == "custom":
                    # Custom stages are designed in the stage builder, never
                    # generated blindly from this list. Open it after saving.
                    builder = format_wizard.create(
                        {
                            "edition_id": edition.id,
                            "division_id": division.id,
                            "participant_set_id": participant_set.id,
                            "format_type": "custom",
                        }
                    ).action_open_stage_builder()
                    builder_actions.append(builder)
                    continue
                format_wizard.create(
                    {
                        "edition_id": edition.id,
                        "division_id": division.id,
                        "participant_set_id": participant_set.id,
                        "format_type": line.format_type,
                        "pool_count": line.pool_count,
                        "preview_confirmed": True,
                    }
                ).action_apply()
            except ValidationError as error:
                raise ValidationError(
                    "%s: %s" % (line.name, error.args[0] if error.args else error)
                ) from error
        if builder_actions:
            return builder_actions[0]
        return edition.action_open_competition_planner()


class FederationCompetitionDivisionSetupLine(models.TransientModel):
    _name = "federation.competition.division.setup.line"
    _description = "Competition Teams and Format Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "federation.competition.division.setup.wizard", required=True, ondelete="cascade"
    )
    division_id = fields.Many2one("federation.tournament", readonly=True)
    name = fields.Char(string="Division", required=True)
    category = fields.Selection(
        selection=lambda self: self.env["federation.tournament"]._fields["category"].selection,
        string="Category",
    )
    gender = fields.Selection(
        selection=lambda self: self.env["federation.tournament"]._fields["gender"].selection,
        string="Gender",
    )
    eligible_team_ids = fields.Many2many(
        "federation.team", compute="_compute_eligible_team_ids"
    )
    team_ids = fields.Many2many(
        "federation.team",
        "federation_division_setup_line_team_rel",
        "line_id",
        "team_id",
        string="Teams",
        domain="[('id', 'in', eligible_team_ids)]",
    )
    format_type = fields.Selection(
        FORMAT_SELECTION, required=True, default="single_round_robin", string="Format"
    )
    pool_count = fields.Integer(default=2, string="Groups")
    team_count = fields.Integer(compute="_compute_preview", string="Teams #")
    match_count = fields.Integer(compute="_compute_preview", string="Matches")
    feasibility_message = fields.Char(compute="_compute_preview", string="Check")

    @api.depends("division_id", "category", "gender")
    def _compute_eligible_team_ids(self):
        Team = self.env["federation.team"]
        for line in self:
            division = line.division_id
            if (
                division
                and (division.category or False) == (line.category or False)
                and (division.gender or False) == (line.gender or False)
            ):
                # Stored scope: also applies the division's rule-set limits.
                line.eligible_team_ids = division.search_eligible_teams(
                    extra_domain=[("active", "=", True)]
                )
                continue
            domain = [("active", "=", True)]
            if line.category:
                domain.append(("category", "=", line.category))
            if line.gender:
                domain.append(("gender", "=", line.gender))
            line.eligible_team_ids = Team.search(domain)

    @api.onchange("category", "gender")
    def _onchange_scope_drop_ineligible_teams(self):
        for line in self:
            line.team_ids = line.team_ids & line.eligible_team_ids

    @api.depends("team_ids", "format_type", "pool_count")
    def _compute_preview(self):
        feasibility = self.env["federation.format.feasibility"]
        for line in self:
            count = len(line.team_ids)
            line.team_count = count
            if count < 2:
                line.match_count = 0
                line.feasibility_message = _("Select at least two teams") if count else False
                continue
            if line.format_type == "custom":
                line.match_count = 0
                line.feasibility_message = _("Built in the stage builder")
                continue
            estimate = feasibility.estimate(line.format_type, count, pool_count=line.pool_count)
            line.match_count = estimate.get("fixture_count", 0)
            line.feasibility_message = (
                False if estimate.get("feasible", True) else estimate.get("message")
            )
