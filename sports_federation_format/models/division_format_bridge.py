"""Divisions built in the competition workspace use their format, not legacy stages.

The workspace stores a division's format as a frozen
``federation.competition.structure`` with ``federation.structure.stage``
records.  The division (``federation.tournament``) form, its Start button and
its lifecycle still only knew the older ``federation.tournament.stage``
records, so a workspace division showed no stages, could not be started and
stayed in draft, which in turn kept it off the website.

This bridge makes the frozen format the source of truth for those divisions:

* the division exposes its current format and format stages (read only);
* Start accepts a frozen format instead of legacy stages;
* divisions with a frozen format follow the competition lifecycle
  (open, in progress, closed) automatically.

Divisions set up the old way, with legacy stages, behave exactly as before.
"""

from html import escape

from odoo import _, fields, models
from odoo.exceptions import ValidationError

DIVISION_STATE_FOR_COMPETITION = {
    "open": ("draft", "open"),
    "in_progress": ("draft", "open", "in_progress"),
    "closed": ("draft", "open", "in_progress", "closed"),
}


class FederationTournamentFormatBridge(models.Model):
    _inherit = "federation.tournament"

    format_structure_id = fields.Many2one(
        "federation.competition.structure",
        compute="_compute_format_structure",
        string="Format",
    )
    format_stage_summary = fields.Html(
        compute="_compute_format_structure",
        string="Format stage summary",
        sanitize=True,
    )
    format_type_label = fields.Char(
        compute="_compute_format_structure", string="Plays as"
    )
    has_workspace_format = fields.Boolean(compute="_compute_format_structure")

    def _compute_format_structure(self):
        Structure = self.env["federation.competition.structure"].sudo()
        frozen = Structure.search(
            [("division_id", "in", self.ids), ("state", "=", "frozen")],
            order="division_id,version desc,id desc",
        )
        latest = {}
        for structure in frozen:
            latest.setdefault(structure.division_id.id, structure)
        labels = dict(
            self.env["federation.competition.structure"].fields_get(["format_type"])[
                "format_type"
            ]["selection"]
        )
        for division in self:
            structure = latest.get(division.id, Structure.browse())
            structure = structure.with_env(self.env)
            division.format_structure_id = structure
            division.format_stage_summary = division._format_stage_summary(
                structure.sudo()
            )
            division.format_type_label = (
                labels.get(structure.sudo().format_type) if structure else False
            )
            division.has_workspace_format = bool(structure)

    @staticmethod
    def _format_stage_summary(structure):
        if not structure:
            return False
        stage_labels = dict(structure.stage_ids._fields["stage_type"].selection)
        rows = []
        for stage in structure.stage_ids.sorted(lambda item: (item.sequence, item.id)):
            matches = len(
                structure.fixture_ids.filtered(
                    lambda fixture, stage=stage: fixture.stage_id == stage
                )
            )
            rows.append(
                "<li><strong>%s</strong> &#8212; %s, %s</li>"
                % (
                    escape(stage.name or ""),
                    escape(stage_labels.get(stage.stage_type, stage.stage_type or "")),
                    escape(structure.env._("%(count)s matches", count=matches)),
                )
            )
        return "<ul class='mb-0'>%s</ul>" % "".join(rows) if rows else False

    def action_start(self):
        """Start workspace divisions on their frozen format; legacy ones as before."""
        workspace = self.filtered(
            lambda division: division.has_workspace_format and not division.stage_ids
        )
        legacy = self - workspace
        if workspace:
            not_open = workspace.filtered(lambda division: division.state != "open")
            if not_open:
                raise ValidationError(_("Only open tournaments can be started."))
            workspace.write({"state": "in_progress"})
        if legacy:
            return super(FederationTournamentFormatBridge, legacy).action_start()
        return True

    def _follow_competition_state(self, target):
        """Move workspace divisions forward to the competition's state.

        Called from the competition's guarded lifecycle transition, so the
        elevated write is limited to the state of divisions in that
        competition that already have a frozen format.  Divisions are never
        moved backwards and cancelled divisions are left alone.
        """
        sources = DIVISION_STATE_FOR_COMPETITION.get(target)
        if not sources:
            return False
        divisions = self.sudo().filtered(
            lambda division: division.active
            and division.has_workspace_format
            and division.state in sources
            and division.state != target
        )
        if divisions:
            divisions.write({"state": target})
        return bool(divisions)

    def action_open_division_format(self):
        """Open the workspace teams & format editor for this division's competition."""
        self.ensure_one()
        edition = self.edition_id
        if not edition:
            raise ValidationError(_("This division does not belong to a competition."))
        if hasattr(edition, "action_setup_teams_and_format"):
            return edition.action_setup_teams_and_format()
        return edition.get_formview_action()


class FederationCompetitionEditionDivisionLifecycle(models.Model):
    _inherit = "federation.competition.edition"

    def transition_competition_state(self, target, reason=False):
        result = super().transition_competition_state(target, reason=reason)
        for edition in self:
            if edition.state == target:
                edition.tournament_ids._follow_competition_state(target)
        return result


class FederationCompetitionStructureDivisionLifecycle(models.Model):
    _inherit = "federation.competition.structure"

    def action_freeze(self):
        """A division whose format is confirmed late catches up with its competition."""
        result = super().action_freeze()
        for structure in self:
            division = structure.division_id
            edition = structure.edition_id
            if division and edition and edition.state in DIVISION_STATE_FOR_COMPETITION:
                division.invalidate_recordset(["has_workspace_format"])
                division._follow_competition_state(edition.state)
        return result
