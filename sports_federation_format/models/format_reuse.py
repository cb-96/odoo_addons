"""Reuse a competition format: snapshots, saved templates and next seasons.

A snapshot is a plain JSON description of a format: the guided options and,
for custom formats, every stage and every link between stages. Teams,
matches and results are never part of it, so a snapshot can be applied to
any later edition with any set of teams.
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SNAPSHOT_VERSION = 1

# Guided options stored on a structure. Kept in one place so templates,
# copies to a new season and the format wizard stay in sync.
OPTION_FIELDS = (
    "pool_count",
    "qualifiers_per_pool",
    "knockout_full_placement",
    "split_rank",
    "first_phase_double",
    "second_phase_double",
    "second_phase_carryover",
    "series_length",
    "swiss_round_count",
)

STAGE_FIELDS = (
    "stage_type",
    "format_type",
    "source_type",
    "carryover_policy",
    "final_rank_from",
    "final_rank_to",
)


class FederationCompetitionStructureReuse(models.Model):
    _inherit = "federation.competition.structure"

    def _stage_label(self, stage):
        """Stage name without the "<format name> - " prefix of generated stages."""
        prefix = "%s - " % (self.name or "")
        name = stage.name or ""
        return (
            name[len(prefix) :] if prefix.strip() and name.startswith(prefix) else name
        )

    def _format_snapshot(self):
        """JSON description of this format, without teams or matches."""
        self.ensure_one()
        stages = self.stage_ids.sorted(lambda stage: (stage.sequence, stage.id))
        keys = {stage.id: index for index, stage in enumerate(stages, 1)}
        links = self.env["federation.structure.stage.progression"].search(
            [("structure_id", "=", self.id), ("active", "=", True)],
            order="source_stage_id,rank_from,id",
        )
        return {
            "version": SNAPSHOT_VERSION,
            "format_type": self.format_type,
            "team_count": len(self.participant_set_id.line_ids),
            "options": {
                name: self[name] for name in OPTION_FIELDS if name in self._fields
            },
            "stages": [
                {
                    "key": keys[stage.id],
                    "name": self._stage_label(stage),
                    "sequence": stage.sequence,
                    **{name: stage[name] or False for name in STAGE_FIELDS},
                }
                for stage in stages
            ],
            "links": [
                {
                    "source": keys[link.source_stage_id.id],
                    "target": keys[link.target_stage_id.id],
                    "rank_from": link.rank_from,
                    "rank_to": link.rank_to,
                    "target_seed_from": link.target_seed_from,
                }
                for link in links
                if link.source_stage_id.id in keys and link.target_stage_id.id in keys
            ],
        }

    @api.model
    def _snapshot_values(self, snapshot):
        """Structure values (format type and options) from a snapshot."""
        if not isinstance(snapshot, dict) or not snapshot.get("format_type"):
            raise ValidationError(_("This saved format cannot be read."))
        values = {"format_type": snapshot["format_type"]}
        for name, value in (snapshot.get("options") or {}).items():
            if name in OPTION_FIELDS and name in self._fields:
                values[name] = value
        return values

    def _apply_format_snapshot(self, snapshot):
        """Rebuild the stages and links of a custom snapshot on a draft format.

        Guided formats need no stages: generating the format builds them from
        the options for the actual number of teams.
        """
        self.ensure_one()
        if self.state != "draft":
            raise ValidationError(_("Only a draft format can receive saved stages."))
        if self.stage_ids:
            raise ValidationError(_("This format already has stages."))
        if self.format_type != "custom":
            return self.env["federation.structure.stage"]
        Stage = self.env["federation.structure.stage"]
        created = {}
        for item in sorted(
            snapshot.get("stages") or (),
            key=lambda row: (row.get("sequence") or 0, row["key"]),
        ):
            values = {
                "name": item.get("name") or _("Stage %s", item["key"]),
                "structure_id": self.id,
                "sequence": item.get("sequence") or item["key"] * 10,
            }
            for name in STAGE_FIELDS:
                if item.get(name) not in (None, False) and name in Stage._fields:
                    values[name] = item[name]
            created[item["key"]] = Stage.create(values)
        for link in snapshot.get("links") or ():
            source, target = created.get(link["source"]), created.get(link["target"])
            if not source or not target:
                continue
            self.env["federation.structure.stage.progression"].create(
                {
                    "name": _(
                        "Places %(start)s-%(end)s of %(source)s to %(target)s",
                        start=link["rank_from"],
                        end=link["rank_to"],
                        source=source.name,
                        target=target.name,
                    ),
                    "source_stage_id": source.id,
                    "target_stage_id": target.id,
                    "rank_from": link["rank_from"],
                    "rank_to": link["rank_to"],
                    "target_seed_from": link.get("target_seed_from") or 1,
                }
            )
        return Stage.browse([stage.id for stage in created.values()])

    def _has_planned_history(self):
        """True when matches of this format are on game days or played."""
        self.ensure_one()
        fixtures = self.fixture_ids
        if not fixtures:
            return False
        if fixtures.filtered(lambda fixture: fixture.state == "completed"):
            return True
        if "federation.matchday.allocation" in self.env:
            allocations = self.env["federation.matchday.allocation"].search(
                [("structure_id", "=", self.id)]
            )
            if allocations.mapped("fixture_ids") & fixtures:
                return True
        return False

    def action_new_draft_version(self):
        """Copy this format (stages and links) into a new editable version."""
        self.ensure_one()
        self.check_access("write")
        if self.state == "draft":
            return self
        if self._has_planned_history():
            raise ValidationError(
                _(
                    "Matches of this format are already on game days or played. "
                    "Clear their planning first, or keep this format."
                )
            )
        latest = self.search(
            [("division_id", "=", self.division_id.id)],
            order="version desc,id desc",
            limit=1,
        )
        snapshot = self._format_snapshot()
        draft = self.create(
            {
                "name": self.name,
                "edition_id": self.edition_id.id,
                "division_id": self.division_id.id,
                "participant_set_id": self.participant_set_id.id,
                "version": (latest.version or 0) + 1,
                **self._snapshot_values(snapshot),
                # A copied guided format keeps its stages so it can be edited.
                "format_type": "custom",
            }
        )
        draft._apply_format_snapshot(snapshot)
        return draft

    def action_save_as_template(self, name=False):
        """Save this format so it can be chosen again next season."""
        self.ensure_one()
        self.check_access("read")
        label = (name or "").strip() or self.name
        if len(label) > 120:
            raise ValidationError(_("Use a shorter template name."))
        code = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "format"
        Template = self.env["federation.competition.format.template"]
        previous = Template.with_context(active_test=False).search(
            [("code", "=", code)], order="version desc", limit=1
        )
        snapshot = self._format_snapshot()
        return Template.create(
            {
                "name": label,
                "code": code,
                "version": (previous.version or 0) + 1,
                "format_type": self.format_type,
                "pool_count": max(self.pool_count or 1, 1),
                "series_length": self.series_length or "1",
                "swiss_round_count": max(self.swiss_round_count or 1, 1),
                "configuration": snapshot,
                "notes": _(
                    "Saved from %(format)s (%(edition)s).",
                    format=self.display_name,
                    edition=self.edition_id.display_name,
                ),
            }
        )


class FederationCompetitionFormatTemplateReuse(models.Model):
    _inherit = "federation.competition.format.template"

    format_type = fields.Selection(
        selection_add=[("custom", "Custom stages")],
        ondelete={"custom": "cascade"},
    )
    stage_summary = fields.Char(compute="_compute_stage_summary")

    @api.depends("configuration", "format_type")
    def _compute_stage_summary(self):
        labels = dict(self.fields_get(["format_type"])["format_type"]["selection"])
        for template in self:
            stages = (template.configuration or {}).get("stages") or []
            template.stage_summary = (
                " → ".join(stage.get("name") or "" for stage in stages[:6])
                if stages and template.format_type == "custom"
                else labels.get(template.format_type, "")
            )

    def _snapshot(self):
        """Snapshot of this template; older templates only have options."""
        self.ensure_one()
        snapshot = dict(self.configuration or {})
        snapshot.setdefault("format_type", self.format_type)
        options = dict(snapshot.get("options") or {})
        options.setdefault("pool_count", self.pool_count)
        options.setdefault("series_length", self.series_length)
        options.setdefault("swiss_round_count", self.swiss_round_count)
        snapshot["options"] = options
        return snapshot

    def action_create_structure(self, edition, division, participant_set):
        self.ensure_one()
        Structure = self.env["federation.competition.structure"]
        latest = Structure.search(
            [("division_id", "=", division.id)], order="version desc,id desc", limit=1
        )
        snapshot = self._snapshot()
        structure = Structure.create(
            {
                "name": f"{edition.display_name} - {self.name} v{self.version}",
                "edition_id": edition.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "version": (latest.version or 0) + 1,
                **Structure._snapshot_values(snapshot),
                "template_id": self.id,
            }
        )
        structure._apply_format_snapshot(snapshot)
        return structure


class FederationDivisionFormatReuse(models.Model):
    _inherit = "federation.tournament"

    format_source_structure_id = fields.Many2one(
        "federation.competition.structure",
        string="Reuse format from",
        ondelete="set null",
        copy=False,
        help="Format of an earlier season offered when this division chooses its format.",
    )
