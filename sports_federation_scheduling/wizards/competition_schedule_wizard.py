import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionScheduleWizard(models.TransientModel):
    _name = "federation.competition.schedule.wizard"
    _description = "Generate Complete Competition Schedule"

    edition_id = fields.Many2one("federation.competition.edition", required=True)
    matchday_ids = fields.Many2many(
        "federation.matchday",
        relation="federation_comp_schedule_wizard_matchday_rel",
        column1="wizard_id",
        column2="matchday_id",
        required=True,
        string="Game Days",
        domain="[('edition_id', '=', edition_id)]",
    )
    structure_ids = fields.Many2many(
        "federation.competition.structure",
        relation="federation_comp_schedule_wizard_structure_rel",
        column1="wizard_id",
        column2="structure_id",
        required=True,
        domain="[('edition_id', '=', edition_id), ('state', 'in', ('draft', 'generated', 'frozen'))]",
    )
    mode = fields.Selection(
        [
            ("fill", "Fill Missing Planning"),
            ("replace_auto", "Replace Automatic Planning"),
            ("rebuild", "Rebuild Unpublished Planning"),
        ],
        default="fill",
        required=True,
    )
    rebuild_reason = fields.Text()
    generate_missing_fixtures = fields.Boolean(default=True)
    preferred_rest_minutes = fields.Integer(default=40, required=True)
    preview_ready = fields.Boolean(readonly=True)
    preview_signature = fields.Char(readonly=True)
    feasibility_report = fields.Json(readonly=True)
    quality_report = fields.Json(readonly=True)
    blocking_issue_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)

    @api.onchange("edition_id")
    def _onchange_edition_id(self):
        if not self.edition_id:
            self.matchday_ids = False
            self.structure_ids = False
            return
        self.matchday_ids = self.env["federation.matchday"].search(
            [("edition_id", "=", self.edition_id.id), ("state", "in", ("draft", "capacity_ready"))],
            order="date,id",
        )
        candidates = self.env["federation.competition.structure"].search(
            [("edition_id", "=", self.edition_id.id), ("state", "in", ("draft", "generated", "frozen"))],
            order="division_id,version desc,id desc",
        )
        latest = self.env["federation.competition.structure"]
        seen = set()
        for structure in candidates:
            if structure.division_id.id not in seen:
                latest |= structure
                seen.add(structure.division_id.id)
        self.structure_ids = latest

    @api.constrains("preferred_rest_minutes", "mode", "rebuild_reason")
    def _check_configuration(self):
        for wizard in self:
            if wizard.preferred_rest_minutes < 0:
                raise ValidationError(_("Preferred rest cannot be negative."))
            if wizard.mode == "rebuild" and not (wizard.rebuild_reason or "").strip():
                raise ValidationError(_("Explain why unpublished planning is rebuilt."))

    def action_preview(self):
        self.ensure_one()
        proposal = self._build_proposal()
        self.write(
            {
                "preview_ready": True,
                "preview_signature": self._input_signature(),
                "feasibility_report": proposal["feasibility"],
                "quality_report": proposal["quality"],
                "blocking_issue_count": len(proposal["errors"]),
                "warning_count": len(proposal["warnings"]),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        if not self.preview_ready:
            raise ValidationError(_("Preview the competition schedule before applying it."))
        if self.preview_signature != self._input_signature():
            raise ValidationError(_("Competition planning changed after preview. Preview again."))
        proposal = self._build_proposal()
        if proposal["errors"]:
            raise ValidationError("\n".join(proposal["errors"]))
        self._prepare_existing_planning()
        self._prepare_structures()
        proposal = self._build_proposal(require_generated=True)
        if proposal["errors"]:
            raise ValidationError("\n".join(proposal["errors"]))
        schedules = self.env["federation.schedule"]
        for day in self.matchday_ids.sorted(lambda item: (item.date, item.id)):
            fixture_ids = proposal["distribution"]["assignments"].get(day.id, [])
            if not fixture_ids:
                continue
            self._generate_day_slots(day)
            fixtures = self.env["federation.fixture"].browse(fixture_ids)
            self._create_allocations(day, fixtures)
            day.action_capacity_ready()
            schedule = self._schedule_for_day(day, fixtures)
            self.env["federation.schedule.auto.wizard"].create(
                {"schedule_id": schedule.id, "preferred_rest_minutes": self.preferred_rest_minutes}
            ).action_apply()
            schedule.invalidate_recordset()
            if schedule.unassigned_fixture_ids:
                raise ValidationError(_("%s still has unscheduled fixtures.") % day.display_name)
            schedules |= schedule
        return {
            "type": "ir.actions.act_window",
            "res_model": "federation.schedule",
            "view_mode": "list,form",
            "domain": [("id", "in", schedules.ids)],
        }

    def _build_proposal(self, require_generated=False):
        errors, warnings = self._validate_scope(require_generated)
        fixtures, deferred = self._fixtures()
        capacities = self._capacities(errors)
        distribution = self.env["federation.competition.schedule.distributor"].propose(
            fixtures, capacities, pinned=self._pinned_fixture_days()
        ) if capacities else {"assignments": {}, "remaining_capacity": {}, "errors": [], "valid": False}
        errors.extend(distribution["errors"])
        duplicate_team_days = self._duplicate_team_days(fixtures, distribution)
        if duplicate_team_days:
            warnings.append(_("Some teams play more than once on a game day."))
        total_capacity = sum(day["capacity"] for day in capacities)
        return {
            "errors": errors,
            "warnings": warnings,
            "distribution": distribution,
            "feasibility": {
                "fixture_count": len(fixtures),
                "deferred_fixture_count": len(deferred),
                "available_slot_count": total_capacity,
                "capacity_surplus": total_capacity - len(fixtures),
                "game_days": capacities,
                "errors": errors,
            },
            "quality": {
                "warnings": warnings,
                "teams_with_multiple_same_day_matches": duplicate_team_days,
                "planned_fixture_counts": {
                    str(day_id): len(ids) for day_id, ids in distribution["assignments"].items()
                },
                "remaining_capacity": distribution["remaining_capacity"],
            },
        }

    def _validate_scope(self, require_generated=False):
        errors, warnings = [], []
        if not self.matchday_ids or not self.structure_ids:
            errors.append(_("Select competition structures and game days."))
        for structure in self.structure_ids:
            if structure.state == "draft" and (require_generated or not self.generate_missing_fixtures):
                errors.append(_("Generate fixtures for %s.") % structure.display_name)
            elif structure.state == "draft":
                warnings.append(_("Fixtures for %s will be generated on apply.") % structure.display_name)
        for day in self.matchday_ids:
            if day.state not in ("draft", "capacity_ready"):
                errors.append(_("%s is no longer mutable.") % day.display_name)
            if not day.planning_court_ids:
                errors.append(_("Select planning courts for %s.") % day.display_name)
            schedules = self.env["federation.schedule"].search([("matchday_id", "=", day.id)])
            if schedules.filtered(lambda schedule: schedule.state not in ("draft", "changes_requested")):
                errors.append(_("%s has reviewed or published planning.") % day.display_name)
            if self.mode == "fill" and (day.slot_ids or day.allocation_ids or schedules):
                warnings.append(_("Existing planning on %s will be retained.") % day.display_name)
        return errors, warnings

    def _fixtures(self):
        all_fixtures = self.structure_ids.mapped("fixture_ids")
        playable = all_fixtures.filtered(
            lambda fixture: fixture.home_team_id and fixture.away_team_id and fixture.state != "cancelled"
        )
        return playable, all_fixtures - playable

    def _capacities(self, errors):
        capacities = []
        generator = self.env["federation.slot.generator"]
        for day in self.matchday_ids.sorted(lambda item: (item.date, item.id)):
            if not day.planning_court_ids:
                continue
            try:
                plan = generator.plan(
                    day, day.planning_court_ids, day.default_day_start_hour,
                    day.default_day_end_hour, day.default_slot_duration_minutes,
                    noon_pause=day.default_noon_pause,
                    noon_pause_minutes=day.default_noon_pause_minutes,
                )
            except ValidationError as exc:
                errors.append("%s: %s" % (day.display_name, exc))
                continue
            retained = len(day.slot_ids.filtered(lambda slot: slot.state == "available")) if self.mode == "fill" else 0
            capacities.append(
                {"matchday_id": day.id, "date": day.date,
                 "capacity": retained or len(plan["available"]), "blocked": plan["blocked_count"]}
            )
        return capacities

    def _pinned_fixture_days(self):
        pinned = {}
        if self.mode == "fill":
            for day in self.matchday_ids:
                for fixture in day.allocation_ids.mapped("manual_fixture_ids"):
                    pinned[fixture.id] = day.id
        return pinned

    def _duplicate_team_days(self, fixtures, distribution):
        by_id = {fixture.id: fixture for fixture in fixtures}
        total = 0
        for fixture_ids in distribution["assignments"].values():
            counts = {}
            for fixture_id in fixture_ids:
                fixture = by_id[fixture_id]
                for team in (fixture.home_team_id, fixture.away_team_id):
                    counts[team.id] = counts.get(team.id, 0) + 1
            total += sum(1 for count in counts.values() if count > 1)
        return total

    def _prepare_existing_planning(self):
        if self.mode == "fill":
            return
        for day in self.matchday_ids:
            schedules = self.env["federation.schedule"].search([("matchday_id", "=", day.id)])
            if self.mode == "replace_auto":
                schedules.mapped("assignment_ids").filtered(lambda item: item.method == "automatic").unlink()
            else:
                schedules.unlink()
                day.allocation_ids.unlink()
                day.slot_ids.unlink()
                day.state = "draft"

    def _prepare_structures(self):
        for structure in self.structure_ids:
            if structure.state == "draft":
                structure.action_generate()
            if structure.state == "generated":
                structure.action_freeze()

    def _generate_day_slots(self, day):
        if day.slot_ids and self.mode in ("fill", "replace_auto"):
            return
        self.env["federation.slot.generator"].generate_plan(
            day, day.planning_court_ids, day.default_day_start_hour,
            day.default_day_end_hour, day.default_slot_duration_minutes,
            noon_pause=day.default_noon_pause,
            noon_pause_minutes=day.default_noon_pause_minutes,
            replace_existing=bool(day.slot_ids),
        )

    def _create_allocations(self, day, fixtures):
        for structure in fixtures.mapped("structure_id"):
            allocated = fixtures.filtered(lambda fixture: fixture.structure_id == structure)
            current = day.allocation_ids.filtered(lambda item: item.structure_id == structure)[:1]
            if current:
                current.manual_fixture_ids |= allocated
            else:
                self.env["federation.matchday.allocation"].create(
                    {"matchday_id": day.id, "structure_id": structure.id,
                     "manual_fixture_ids": [(6, 0, allocated.ids)]}
                )

    def _schedule_for_day(self, day, fixtures):
        schedule = self.env["federation.schedule"].search(
            [("matchday_id", "=", day.id), ("state", "in", ("draft", "changes_requested"))], limit=1
        )
        return schedule or self.env["federation.schedule"].create(
            {"name": _("%s schedule") % day.display_name, "edition_id": self.edition_id.id,
             "structure_id": fixtures[:1].structure_id.id, "matchday_id": day.id,
             "preferred_rest_minutes": self.preferred_rest_minutes}
        )

    def _input_signature(self):
        payload = {
            "edition": self.edition_id.id,
            "structures": [(item.id, item.state, item.version, item.write_date) for item in self.structure_ids],
            "days": [(day.id, day.state, day.date, day.default_day_start_hour,
                      day.default_day_end_hour, day.default_slot_duration_minutes,
                      day.planning_court_ids.ids, day.write_date) for day in self.matchday_ids],
            "mode": self.mode,
        }
        return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()
