from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sports_federation_format.services import format_presets

FORMAT_CHOICES = [
    ("single_round_robin", "League"),
    ("double_round_robin", "Home & away league"),
    ("knockout", "Knockout"),
    ("pool_knockout", "Groups, then knockout"),
    ("split_pools", "Regular season, then split"),
    ("custom", "Custom stages"),
]

FORMAT_HINTS = {
    "single_round_robin": "Every team plays every other team once. One table decides the ranking.",
    "double_round_robin": "Every team plays every other team twice, home and away.",
    "knockout": "Lose and you are out. Byes are given when the team count is not a power of two.",
    "pool_knockout": "Teams play a round robin in groups. The best of every group reach a cross-seeded knockout.",
    "split_pools": "Everyone plays a regular season. The table is then split into a top and bottom group that play a second round robin. Put every team in the top group to play a season in two halves.",
    "custom": "Build your own stages and links between them, for example a third-place group or extra placement matches.",
}

# Structure options the guided formats use; a structure is reused only when
# every option matches.
OPTION_FIELDS = (
    "pool_count",
    "qualifiers_per_pool",
    "knockout_full_placement",
    "split_rank",
    "first_phase_double",
    "second_phase_double",
    "second_phase_carryover",
)


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
        FORMAT_CHOICES,
        required=True,
        default="single_round_robin",
        string="Format",
    )
    format_hint = fields.Char(compute="_compute_format_hint")
    pool_count = fields.Integer(default=2, required=True, string="Number of groups")
    qualifiers_per_pool = fields.Integer(
        default=2, required=True, string="Teams per group to the knockout"
    )
    knockout_full_placement = fields.Boolean(
        string="Play for every place",
        help="Teams knocked out keep playing classification matches so every final place is decided.",
    )
    split_rank = fields.Integer(
        string="Teams in the top group",
        help="Places 1 to this number form the top group, the rest the bottom group. "
        "Use the number of teams to play a second half with everyone.",
    )
    first_phase_double = fields.Boolean(
        string="Home & away in the first stage",
        help="Groups or the regular season play every opponent twice.",
    )
    second_phase_double = fields.Boolean(
        string="Home & away after the split",
    )
    second_phase_carryover = fields.Selection(
        [
            ("none", "Start from zero"),
            ("same_group_results", "Keep results between teams of the same group"),
            ("full_points", "Keep all regular-season points"),
        ],
        string="Points after the split",
        default="none",
        required=True,
    )

    preview_match_count = fields.Integer(compute="_compute_format_preview", string="Total matches")
    preview_matches_per_team = fields.Integer(compute="_compute_format_preview", string="Matches per team (league)")
    preview_byes = fields.Integer(compute="_compute_format_preview", string="First-round byes")
    preview_feasible = fields.Boolean(compute="_compute_format_preview")
    preview_message = fields.Char(compute="_compute_format_preview", string="Check")
    preview_outline = fields.Html(
        compute="_compute_format_preview", string="How it plays", sanitize=True
    )
    preview_confirmed = fields.Boolean(string="I have reviewed this format")
    template_id = fields.Many2one(
        "federation.competition.format.template",
        string="Start from a saved format",
        domain="[('active', '=', True)]",
        help="Fill in a format saved earlier. You can still change every option.",
    )
    has_templates = fields.Boolean(compute="_compute_has_templates")
    source_structure_id = fields.Many2one(
        "federation.competition.structure",
        string="Last season's format",
        readonly=True,
        help="This division was copied from an earlier season; its format is filled in.",
    )

    def _compute_has_templates(self):
        has_templates = bool(
            self.env["federation.competition.format.template"].search_count([], limit=1)
        )
        for wizard in self:
            wizard.has_templates = has_templates

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if not self.template_id:
            return
        snapshot = self.template_id._snapshot()
        values = self._choice_from_values(
            snapshot.get("format_type"), snapshot.get("options") or {}
        )
        for name, value in values.items():
            self[name] = value
        self.source_structure_id = False
        self.preview_confirmed = False

    @api.depends("format_type")
    def _compute_format_hint(self):
        for wizard in self:
            wizard.format_hint = FORMAT_HINTS.get(wizard.format_type, "")

    @api.depends(
        "participant_set_id.line_ids",
        "format_type",
        "pool_count",
        "qualifiers_per_pool",
        "knockout_full_placement",
        "split_rank",
        "first_phase_double",
        "second_phase_double",
    )
    def _compute_format_preview(self):
        for wizard in self:
            n = len(wizard.participant_set_id.line_ids)
            plan = format_presets.plan(
                wizard.format_type,
                n,
                pool_count=wizard.pool_count,
                qualifiers_per_pool=wizard.qualifiers_per_pool,
                knockout_full_placement=wizard.knockout_full_placement,
                split_rank=wizard.split_rank or (n + 1) // 2,
                first_phase_double=wizard.first_phase_double,
                second_phase_double=wizard.second_phase_double,
            )
            multiplier = 2 if wizard.format_type == "double_round_robin" else 1
            wizard.preview_feasible = plan["feasible"]
            wizard.preview_message = plan["message"]
            wizard.preview_match_count = plan["fixture_count"]
            wizard.preview_matches_per_team = (
                max(n - 1, 0) * multiplier
                if wizard.format_type in ("single_round_robin", "double_round_robin")
                else 0
            )
            wizard.preview_byes = (
                (1 << (n - 1).bit_length()) - n
                if n > 1 and wizard.format_type == "knockout"
                else 0
            )
            wizard.preview_outline = wizard._outline_html(plan)

    def _outline_html(self, plan):
        if self.format_type == "custom":
            return (
                "<p class='mb-0'>%s</p>"
                % escape(
                    _(
                        "Open the stage builder, add stages and link the places "
                        "that advance. Then reopen Format options for this "
                        "division and choose Generate All Matches."
                    )
                )
            )
        if not plan["stages"]:
            return False
        chips = []
        for stage in plan["stages"]:
            chips.append(
                "<span class='badge text-bg-light border text-wrap text-start p-2'>"
                "<strong>%s</strong><br/>%s<br/><small class='text-muted'>%s</small></span>"
                % (
                    escape(stage["name"]),
                    escape(
                        _(
                            "%(teams)s teams · %(matches)s matches",
                            teams=stage["teams"],
                            matches=stage["matches"],
                        )
                    ),
                    escape(stage["source"]),
                )
            )
        # Parallel groups are one step; the next stage follows an arrow.
        if self.format_type == "pool_knockout":
            groups = " ".join(chips[:-1])
            body = "%s <span aria-hidden='true'>→</span> %s" % (groups, chips[-1])
        elif self.format_type == "split_pools":
            body = "%s <span aria-hidden='true'>→</span> %s" % (
                chips[0],
                " ".join(chips[1:]),
            )
        else:
            body = chips[0]
        return "<div class='d-flex flex-wrap align-items-center gap-2'>%s</div>" % body

    @api.onchange(
        "format_type",
        "division_id",
        "pool_count",
        "qualifiers_per_pool",
        "knockout_full_placement",
        "split_rank",
        "first_phase_double",
        "second_phase_double",
        "second_phase_carryover",
    )
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
            values.update(self._starting_choice(edition, division))
        return values

    @api.model_create_multi
    def create(self, vals_list):
        """Opened for a division without a chosen format: start from its
        current format, or from last season's when it was copied."""
        prepared = []
        for vals in vals_list:
            if vals.get("edition_id") and vals.get("division_id"):
                edition = self.env["federation.competition.edition"].browse(vals["edition_id"])
                division = self.env["federation.tournament"].browse(vals["division_id"])
                start = self._starting_choice(edition, division)
                # The same format keeps its options (qualifiers, split point…)
                # even when only the format type is passed, as Teams & format does.
                if "format_type" not in vals or start.get("format_type") == vals["format_type"]:
                    vals = {**start, **vals}
            prepared.append(vals)
        return super().create(prepared)

    @api.model
    def _starting_choice(self, edition, division):
        current = self._current_choice(edition, division)
        if current:
            return current
        source = (
            division.format_source_structure_id
            if "format_source_structure_id" in division._fields
            else False
        )
        if source:
            return {**self._choice_from_structure(source), "source_structure_id": source.id}
        return {}

    @api.model
    def _current_choice(self, edition, division):
        """Reopen the format with the choice the division already has."""
        structure = self.env["federation.competition.structure"].search(
            [
                ("edition_id", "=", edition.id),
                ("division_id", "=", division.id),
                ("state", "in", ("draft", "generated", "frozen")),
            ],
            order="version desc,id desc",
            limit=1,
        )
        if not structure:
            return {}
        return self._choice_from_structure(structure)

    @api.model
    def _choice_from_structure(self, structure):
        return self._choice_from_values(
            structure.format_type, {name: structure[name] for name in OPTION_FIELDS}
        )

    @api.model
    def _choice_from_values(self, format_type, options):
        """Wizard values for a stored format type and its options."""
        values = {
            name: options[name]
            for name in OPTION_FIELDS
            if name in options and options[name] is not None
        }
        if format_type == "placement_bracket":
            format_type = "knockout"
            values["knockout_full_placement"] = True
        if format_type not in dict(FORMAT_CHOICES):
            format_type = "custom"
        values["format_type"] = format_type
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

    def _structure_format_type(self):
        if self.format_type == "knockout" and self.knockout_full_placement:
            return "placement_bracket"
        return self.format_type

    def _structure_options(self):
        """Options stored on the structure; only what this format uses."""
        options = {
            "pool_count": 2,
            "qualifiers_per_pool": 2,
            "knockout_full_placement": False,
            "split_rank": 0,
            "first_phase_double": False,
            "second_phase_double": False,
            "second_phase_carryover": "none",
        }
        if self.format_type == "pool_knockout":
            options.update(
                pool_count=self.pool_count,
                qualifiers_per_pool=self.qualifiers_per_pool,
                knockout_full_placement=self.knockout_full_placement,
                first_phase_double=self.first_phase_double,
            )
        elif self.format_type == "knockout":
            options["knockout_full_placement"] = self.knockout_full_placement
        elif self.format_type == "split_pools":
            options.update(
                split_rank=self.split_rank or (self.team_count + 1) // 2,
                first_phase_double=self.first_phase_double,
                second_phase_double=self.second_phase_double,
                second_phase_carryover=self.second_phase_carryover,
            )
        return options

    def _matching_structure(self, participant_set, format_type, options):
        candidates = self.env["federation.competition.structure"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("division_id", "=", self.division_id.id),
                ("participant_set_id", "=", participant_set.id),
                ("format_type", "=", format_type),
                ("state", "in", ("draft", "generated", "frozen")),
            ],
            order="version desc,id desc",
        )
        if format_type == "custom":
            return candidates[:1]
        return candidates.filtered(
            lambda item: all(item[name] == value for name, value in options.items())
        )[:1]

    def action_apply(self):
        self.ensure_one()
        participant_set = self._latest_participant_set(
            self.edition_id, self.division_id
        )
        if participant_set != self.participant_set_id:
            raise ValidationError(_("The participating teams changed. Reopen and review the format."))
        format_type = self._structure_format_type()
        options = self._structure_options()
        structure = self._matching_structure(participant_set, format_type, options)
        if self.format_type == "custom":
            if self._wants_new_custom(structure) or not structure.stage_ids:
                return self._open_stage_builder(
                    structure
                    if structure and not self._wants_new_custom(structure)
                    else self._create_structure(participant_set, format_type, options)
                )
        if self.format_type != "custom" and not self.preview_confirmed:
            raise ValidationError(_("Review the format preview before confirming."))
        if self.format_type != "custom" and not self.preview_feasible:
            raise ValidationError(self.preview_message)
        if not structure:
            structure = self._create_structure(participant_set, format_type, options)
        if structure.state == "draft":
            structure.action_generate()
        if structure.state == "generated":
            structure.action_freeze()
        if hasattr(self.edition_id, "action_open_competition_planner"):
            return self.edition_id.action_open_competition_planner()
        return structure.get_formview_action()

    def action_open_stage_builder(self):
        """Open (or start) the custom stages of this division."""
        self.ensure_one()
        participant_set = self._latest_participant_set(
            self.edition_id, self.division_id
        )
        structure = self._matching_structure(participant_set, "custom", {})
        if not structure or self._wants_new_custom(structure):
            structure = self._create_structure(
                participant_set, "custom", self._structure_options()
            )
        return self._open_stage_builder(structure)

    def _wants_new_custom(self, structure):
        """A chosen custom template starts a new format unless already used."""
        return bool(
            self.template_id
            and self.template_id.format_type == "custom"
            and (not structure or structure.template_id != self.template_id)
        )

    def _reuse_snapshot(self):
        """Stages to copy into a new custom format: saved template or last season."""
        if self.format_type != "custom":
            return False
        if self.template_id and self.template_id.format_type == "custom":
            return self.template_id._snapshot()
        source = self.source_structure_id
        if source and self._choice_from_structure(source)["format_type"] == "custom":
            return source._format_snapshot()
        return False

    def _create_structure(self, participant_set, format_type, options):
        latest = self.env["federation.competition.structure"].search(
            [("division_id", "=", self.division_id.id)],
            order="version desc,id desc",
            limit=1,
        )
        structure = self.env["federation.competition.structure"].create(
            {
                "name": _("%(division)s format", division=self.division_id.display_name),
                "edition_id": self.edition_id.id,
                "division_id": self.division_id.id,
                "participant_set_id": participant_set.id,
                "version": (latest.version + 1) if latest else 1,
                "format_type": format_type,
                "template_id": self.template_id.id,
                **options,
            }
        )
        snapshot = self._reuse_snapshot()
        if snapshot:
            structure._apply_format_snapshot(snapshot)
        return structure

    def _open_stage_builder(self, structure):
        return structure.action_open_stage_builder()
