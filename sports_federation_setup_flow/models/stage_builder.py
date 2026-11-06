"""Stage builder: design a custom format as stages and links between them.

The builder edits the existing stage graph models (stages and progressions)
of a draft format. It adds no data of its own: everything it shows is
computed from the graph, and every check is repeated when the format is
generated.
"""

from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.sports_federation_format.services import format_presets

BUILDER_FORMATS = (
    ("single_round_robin", "League (play every team once)"),
    ("double_round_robin", "Home & away league"),
    ("knockout", "Knockout"),
    ("placement_bracket", "Knockout, every place played"),
)
STAGE_TYPE_BY_FORMAT = {
    "single_round_robin": "league",
    "double_round_robin": "league",
    "knockout": "knockout",
    "placement_bracket": "placement",
}
CARRYOVER_LABELS = {
    "none": "",
    "same_group_results": "results between these teams count",
    "full_points": "all points carried over",
}
MAX_NAME = 80


class FederationStageBuilder(models.AbstractModel):
    _name = "federation.stage.builder"
    _description = "Competition Stage Builder"

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    @api.model
    def _structure(self, structure_id, editable=False):
        structure = (
            self.env["federation.competition.structure"]
            .browse(int(structure_id or 0))
            .exists()
        )
        if not structure:
            raise ValidationError(_("This format no longer exists."))
        structure.check_access("read")
        if editable:
            structure.check_access("write")
            if structure.state != "draft":
                raise ValidationError(
                    _("This format is already generated. Edit it as a new version.")
                )
        return structure

    @api.model
    def _stage(self, structure, stage_id):
        stage = structure.stage_ids.filtered(lambda item: item.id == int(stage_id or 0))
        if not stage:
            raise ValidationError(_("Choose a stage of this format."))
        return stage

    @api.model
    def _link(self, structure, link_id):
        link = (
            self.env["federation.structure.stage.progression"]
            .browse(int(link_id or 0))
            .exists()
        )
        if not link or link.structure_id != structure:
            raise ValidationError(_("Choose a link of this format."))
        return link

    @api.model
    def _clean_name(self, value):
        name = (value or "").strip()
        if not name:
            raise ValidationError(_("Give the stage a name."))
        if len(name) > MAX_NAME:
            raise ValidationError(
                _("Use a stage name of at most %s characters.", MAX_NAME)
            )
        return name

    @api.model
    def _clean_format(self, value):
        if value not in dict(BUILDER_FORMATS):
            raise ValidationError(_("Choose how this stage is played."))
        return value

    @api.model
    def _positive(self, value, label):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValidationError(_("%s must be a whole number.", label)) from None
        if number < 1 or number > 512:
            raise ValidationError(_("%s must be between 1 and 512.", label))
        return number

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------
    @api.model
    def _team_count(self, structure):
        return len(structure.participant_set_id.line_ids)

    @api.model
    def _stage_size(self, structure, stage):
        if stage.source_type == "progression":
            return sum(
                link.rank_to - link.rank_from + 1
                for link in stage.incoming_progression_ids.filtered("active")
            )
        if stage.source_type == "manual":
            return len(stage.stage_participant_ids)
        return self._team_count(structure)

    @api.model
    def _match_estimate(self, stage, size):
        if stage.stage_fixture_ids:
            return len(stage.stage_fixture_ids.filtered(lambda f: not f.bye_team_id))
        if stage.format_type in ("single_round_robin", "double_round_robin"):
            return format_presets.round_robin_count(
                size, stage.format_type == "double_round_robin"
            )
        if stage.format_type in ("knockout", "placement_bracket"):
            return format_presets.bracket_match_count(
                size, stage.format_type == "placement_bracket"
            )
        return 0

    @api.model
    def _link_sentence(self, link):
        start, end = link.rank_from, link.rank_to
        places = (
            _("Place %s", start)
            if start == end
            else _("Places %(start)s–%(end)s", start=start, end=end)
        )
        sentence = _(
            "%(places)s of %(source)s → %(target)s",
            places=places,
            source=link.source_stage_id.name,
            target=link.target_stage_id.name,
        )
        seed_end = link.target_seed_from + end - start
        if link.target_seed_from != start or seed_end != end:
            sentence += _(
                " as seeds %(start)s–%(end)s", start=link.target_seed_from, end=seed_end
            )
        carry = CARRYOVER_LABELS.get(link.target_stage_id.carryover_policy)
        if carry:
            sentence += ", " + _(carry)
        return sentence

    @api.model
    def _issues(self, structure, sizes):
        issues = []
        stages = structure.stage_ids
        if not stages:
            return [
                {"message": _("Add a first stage. It plays with all registered teams.")}
            ]
        try:
            self.env["federation.stage.graph.validator"].validate(structure)
        except ValidationError:
            issues.append(
                {
                    "message": _(
                        "The links go round in a circle. Remove one link so teams flow forward."
                    )
                }
            )
        if not stages.filtered(
            lambda stage: not stage.incoming_progression_ids.filtered("active")
        ):
            issues.append(
                {
                    "message": _(
                        "Every stage receives teams from another stage. One stage must start with the registered teams."
                    )
                }
            )
        for stage in stages:
            incoming = stage.incoming_progression_ids.filtered("active")
            size = sizes[stage.id]
            if stage.source_type == "progression" and not incoming:
                issues.append(
                    {
                        "stage_id": stage.id,
                        "message": _(
                            "No teams flow into %s yet. Link places of an earlier stage to it.",
                            stage.name,
                        ),
                    }
                )
            elif stage.source_type != "progression" and incoming:
                issues.append(
                    {
                        "stage_id": stage.id,
                        "message": _(
                            "%s starts with registered teams but also receives teams from another stage.",
                            stage.name,
                        ),
                    }
                )
            elif stage.source_type == "manual" and size < 2:
                issues.append(
                    {
                        "stage_id": stage.id,
                        "message": _(
                            "Assign at least two teams to %s on its stage form.",
                            stage.name,
                        ),
                    }
                )
            elif size and size < 2:
                issues.append(
                    {
                        "stage_id": stage.id,
                        "message": _("%s needs at least two teams.", stage.name),
                    }
                )
            if (
                stage.format_type not in dict(BUILDER_FORMATS)
                and stage.format_type != "manual"
            ):
                issues.append(
                    {
                        "stage_id": stage.id,
                        "message": _(
                            "%s uses a format the builder cannot generate.", stage.name
                        ),
                    }
                )
            seeds = []
            for link in incoming:
                seeds.extend(
                    range(
                        link.target_seed_from,
                        link.target_seed_from + link.rank_to - link.rank_from + 1,
                    )
                )
                source_size = sizes.get(link.source_stage_id.id, 0)
                if source_size and link.rank_to > source_size:
                    issues.append(
                        {
                            "link_id": link.id,
                            "message": _(
                                "%(source)s has %(count)s teams, so place %(rank)s does not exist.",
                                source=link.source_stage_id.name,
                                count=source_size,
                                rank=link.rank_to,
                            ),
                        }
                    )
            if seeds and sorted(seeds) != list(range(1, len(seeds) + 1)):
                duplicate = len(set(seeds)) != len(seeds)
                issues.append(
                    {
                        "stage_id": stage.id,
                        "message": (
                            _("Two links give teams the same seed in %s.", stage.name)
                            if duplicate
                            else _(
                                "Seeds in %s should run from 1 without gaps.",
                                stage.name,
                            )
                        ),
                    }
                )
        for source in stages:
            taken = []
            for link in source.outgoing_progression_ids.filtered("active"):
                taken.extend(range(link.rank_from, link.rank_to + 1))
            if len(set(taken)) != len(taken):
                issues.append(
                    {
                        "stage_id": source.id,
                        "message": _(
                            "A place of %s is sent to two stages.", source.name
                        ),
                    }
                )
        return issues

    @api.model
    def load(self, structure_id):
        structure = self._structure(structure_id)
        stages = structure.stage_ids.sorted(lambda stage: (stage.sequence, stage.id))
        depths = stages._planning_depths() if stages else {}
        sizes = {stage.id: self._stage_size(structure, stage) for stage in stages}
        links = self.env["federation.structure.stage.progression"].search(
            [("structure_id", "=", structure.id), ("active", "=", True)],
            order="source_stage_id,rank_from,id",
        )
        issues = self._issues(structure, sizes)
        format_labels = dict(BUILDER_FORMATS)
        format_labels["manual"] = _("Matches added by hand")
        carry_labels = dict(structure.stage_ids._fields["carryover_policy"].selection)
        try:
            structure.check_access("write")
        except AccessError:
            can_write = False
        else:
            can_write = True
        editable = can_write and structure.state == "draft"
        stage_rows = []
        for stage in stages:
            used = sum(
                link.rank_to - link.rank_from + 1
                for link in stage.outgoing_progression_ids.filtered("active")
            )
            stage_rows.append(
                {
                    "id": stage.id,
                    "name": stage.name,
                    "column": depths.get(stage.id, 0),
                    "format_type": stage.format_type,
                    "format_label": format_labels.get(
                        stage.format_type, stage.format_type
                    ),
                    "source_type": stage.source_type,
                    "source_label": (
                        _("Registered teams")
                        if stage.source_type == "registration"
                        else (
                            _("Teams set by hand")
                            if stage.source_type == "manual"
                            else _("From earlier stages")
                        )
                    ),
                    "teams": sizes[stage.id],
                    "matches": self._match_estimate(stage, sizes[stage.id]),
                    "places_free": max(sizes[stage.id] - used, 0),
                    "next_free_place": self._next_free(
                        stage.outgoing_progression_ids.filtered("active"), "rank"
                    ),
                    "next_free_seed": self._next_free(
                        stage.incoming_progression_ids.filtered("active"), "seed"
                    ),
                    "carryover_policy": stage.carryover_policy,
                    "game_days": (
                        ", ".join(stage.matchday_ids.mapped("display_name"))
                        if "matchday_ids" in stage._fields
                        else ""
                    ),
                    "has_issue": any(
                        issue.get("stage_id") == stage.id for issue in issues
                    ),
                }
            )
        columns = max((row["column"] for row in stage_rows), default=-1) + 1
        return {
            "structure": {
                "id": structure.id,
                "name": structure.display_name,
                "division": structure.division_id.display_name,
                "edition_id": structure.edition_id.id,
                "state": structure.state,
                "version": structure.version,
                "team_count": self._team_count(structure),
                "editable": editable,
                "match_count": sum(row["matches"] for row in stage_rows),
                "can_new_version": structure.state != "draft"
                and not structure._has_planned_history(),
                "can_confirm": can_write and structure.state == "generated",
            },
            "columns": columns,
            "stages": stage_rows,
            "links": [
                {
                    "id": link.id,
                    "source_id": link.source_stage_id.id,
                    "target_id": link.target_stage_id.id,
                    "rank_from": link.rank_from,
                    "rank_to": link.rank_to,
                    "target_seed_from": link.target_seed_from,
                    "sentence": self._link_sentence(link),
                    "has_issue": any(
                        issue.get("link_id") == link.id for issue in issues
                    ),
                }
                for link in links
            ],
            "issues": issues,
            "formats": [
                {"key": key, "label": _(label)} for key, label in BUILDER_FORMATS
            ],
            "carryover": [
                {"key": key, "label": label} for key, label in carry_labels.items()
            ],
        }

    @api.model
    def _next_free(self, links, kind):
        taken = set()
        for link in links:
            start = link.rank_from if kind == "rank" else link.target_seed_from
            taken.update(range(start, start + link.rank_to - link.rank_from + 1))
        value = 1
        while value in taken:
            value += 1
        return value

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    @api.model
    def add_stage(self, structure_id, values):
        structure = self._structure(structure_id, editable=True)
        values = values or {}
        format_type = self._clean_format(values.get("format_type"))
        after = values.get("after_stage_id")
        source = (
            self._stage(structure, after)
            if after
            else self.env["federation.structure.stage"]
        )
        sequence = max(structure.stage_ids.mapped("sequence") or [0]) + 10
        stage = self.env["federation.structure.stage"].create(
            {
                "name": self._clean_name(values.get("name")),
                "structure_id": structure.id,
                "sequence": sequence,
                "stage_type": STAGE_TYPE_BY_FORMAT[format_type],
                "format_type": format_type,
                "source_type": "progression" if source else "registration",
            }
        )
        if source:
            size = self._stage_size(structure, source)
            start = self._next_free(
                source.outgoing_progression_ids.filtered("active"), "rank"
            )
            count = self._positive(
                values.get("places") or max(size - start + 1, 2), _("Places")
            )
            self._create_link(structure, source, stage, start, start + count - 1, 1)
        return self.load(structure.id)

    @api.model
    def update_stage(self, structure_id, stage_id, values):
        structure = self._structure(structure_id, editable=True)
        stage = self._stage(structure, stage_id)
        values = values or {}
        update = {}
        if "name" in values:
            update["name"] = self._clean_name(values["name"])
        if "format_type" in values:
            format_type = self._clean_format(values["format_type"])
            update.update(
                format_type=format_type, stage_type=STAGE_TYPE_BY_FORMAT[format_type]
            )
        if "carryover_policy" in values:
            if values["carryover_policy"] not in dict(
                stage._fields["carryover_policy"].selection
            ):
                raise ValidationError(_("Choose how points carry over."))
            update["carryover_policy"] = values["carryover_policy"]
        if update:
            stage.write(update)
        return self.load(structure.id)

    @api.model
    def delete_stage(self, structure_id, stage_id):
        structure = self._structure(structure_id, editable=True)
        # Its links go with it. A stage that loses its only feeder keeps
        # waiting for a new link; the checks show it until it is fixed.
        self._stage(structure, stage_id).unlink()
        return self.load(structure.id)

    @api.model
    def _create_link(self, structure, source, target, rank_from, rank_to, seed_from):
        if source == target:
            raise ValidationError(_("Link two different stages."))
        try:
            with self.env.cr.savepoint():
                return self._create_checked_link(
                    structure, source, target, rank_from, rank_to, seed_from
                )
        except ValidationError:
            self.env.invalidate_all()
            raise

    @api.model
    def _create_checked_link(
        self, structure, source, target, rank_from, rank_to, seed_from
    ):
        link = self.env["federation.structure.stage.progression"].create(
            {
                "name": _(
                    "Places %(start)s-%(end)s of %(source)s to %(target)s",
                    start=rank_from,
                    end=rank_to,
                    source=source.name,
                    target=target.name,
                ),
                "source_stage_id": source.id,
                "target_stage_id": target.id,
                "rank_from": rank_from,
                "rank_to": rank_to,
                "target_seed_from": seed_from,
            }
        )
        if target.source_type != "progression":
            target.source_type = "progression"
        try:
            self.env["federation.stage.graph.validator"].validate(structure)
        except ValidationError:
            raise ValidationError(
                _(
                    "This link would send teams back to an earlier stage. Choose a later stage."
                )
            ) from None
        return link

    @api.model
    def add_link(self, structure_id, values):
        structure = self._structure(structure_id, editable=True)
        values = values or {}
        source = self._stage(structure, values.get("source_id"))
        target = self._stage(structure, values.get("target_id"))
        rank_from = self._positive(values.get("rank_from"), _("First place"))
        rank_to = self._positive(values.get("rank_to") or rank_from, _("Last place"))
        if rank_to < rank_from:
            raise ValidationError(
                _("The last place must not be before the first place.")
            )
        seed_from = values.get("target_seed_from") or self._next_free(
            target.incoming_progression_ids.filtered("active"), "seed"
        )
        self._create_link(
            structure,
            source,
            target,
            rank_from,
            rank_to,
            self._positive(seed_from, _("First seed")),
        )
        return self.load(structure.id)

    @api.model
    def delete_link(self, structure_id, link_id):
        structure = self._structure(structure_id, editable=True)
        self._link(structure, link_id).unlink()
        return self.load(structure.id)

    @api.model
    def generate(self, structure_id):
        """Generate every match and continue in the competition planner.

        A format generated elsewhere but not yet confirmed (frozen) is only
        confirmed here, so it never ends in a dead end.
        """
        structure = self._structure(structure_id)
        structure.check_access("write")
        if structure.state == "draft":
            sizes = {
                stage.id: self._stage_size(structure, stage)
                for stage in structure.stage_ids
            }
            issues = self._issues(structure, sizes)
            if issues:
                raise ValidationError(issues[0]["message"])
            structure.action_generate()
        if structure.state == "generated":
            structure.action_freeze()
        elif structure.state != "frozen":
            raise ValidationError(_("This format can no longer be generated."))
        edition = structure.edition_id
        if hasattr(edition, "action_open_competition_planner"):
            return edition.action_open_competition_planner()
        return structure.get_formview_action()

    @api.model
    def new_version(self, structure_id):
        structure = self._structure(structure_id)
        draft = structure.action_new_draft_version()
        return self.load(draft.id)

    @api.model
    def save_template(self, structure_id, name):
        structure = self._structure(structure_id)
        template = structure.action_save_as_template(name)
        return {"id": template.id, "name": template.display_name}


class FederationCompetitionStructureBuilder(models.Model):
    _inherit = "federation.competition.structure"

    def action_open_stage_builder(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "federation_stage_builder",
            "name": _("Stages: %s", self.division_id.display_name),
            "params": {"structure_id": self.id},
            "target": "current",
        }


class FederationCompetitionScheduleWizardStages(models.TransientModel):
    _inherit = "federation.competition.schedule.wizard"

    def _unfinished_custom_formats(self):
        """Messages for custom drafts whose stages are not complete yet."""
        builder = self.env["federation.stage.builder"]
        messages = []
        for structure in self.structure_ids.filtered(
            lambda item: item.state == "draft" and item.format_type == "custom"
        ):
            sizes = {
                stage.id: builder._stage_size(structure, stage)
                for stage in structure.stage_ids
            }
            issues = builder._issues(structure, sizes)
            if issues:
                messages.append(
                    _(
                        "%(division)s: finish its stages in the stage builder first. %(issue)s",
                        division=structure.division_id.display_name,
                        issue=issues[0]["message"],
                    )
                )
        return messages

    def _validate_scope(self, require_generated=False):
        errors, warnings = super()._validate_scope(require_generated)
        return errors + self._unfinished_custom_formats(), warnings

    def _prepare_structures(self):
        """Planning never generates an unfinished custom format.

        A custom format is generated from the stage builder, which checks its
        stages first. Planning only finishes one whose stages are complete.
        """
        messages = self._unfinished_custom_formats()
        if messages:
            raise ValidationError("\n".join(messages))
        return super()._prepare_structures()
