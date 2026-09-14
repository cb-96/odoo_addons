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
        domain="[('edition_id', '=', edition_id), ('state', 'in', ('draft', 'capacity_ready'))]",
    )
    structure_ids = fields.Many2many(
        "federation.competition.structure",
        relation="federation_comp_schedule_wizard_structure_rel",
        column1="wizard_id",
        column2="structure_id",
        required=True,
        domain="[('edition_id', '=', edition_id), ('state', 'in', ('generated', 'frozen'))]",
    )
    preferred_rest_minutes = fields.Integer(default=40, required=True)
    preview_ready = fields.Boolean(readonly=True)
    preview_report = fields.Text(readonly=True)

    @api.onchange("edition_id")
    def _onchange_edition_id(self):
        if not self.edition_id:
            return
        self.matchday_ids = self.env["federation.matchday"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("state", "in", ("draft", "capacity_ready")),
            ],
            order="date,id",
        )
        candidates = self.env["federation.competition.structure"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("state", "in", ("generated", "frozen")),
            ],
            order="division_id,version desc,id desc",
        )
        latest = self.env["federation.competition.structure"]
        seen = set()
        for structure in candidates:
            if structure.division_id.id not in seen:
                latest |= structure
                seen.add(structure.division_id.id)
        self.structure_ids = latest

    def _validate_inputs(self):
        self.ensure_one()
        if self.preferred_rest_minutes < 0:
            raise ValidationError(_("Preferred rest cannot be negative."))
        for day in self.matchday_ids:
            if day.slot_ids or day.allocation_ids:
                raise ValidationError(
                    _("%s already has planning data.") % day.display_name
                )
            if not day.planning_court_ids:
                raise ValidationError(
                    _("Select planning courts for %s.") % day.display_name
                )
            if self.env["federation.schedule"].search_count(
                [("matchday_id", "=", day.id)]
            ):
                raise ValidationError(
                    _("%s already has a schedule.") % day.display_name
                )

    def _fixtures(self):
        fixtures = self.structure_ids.mapped("fixture_ids").filtered(
            lambda fixture: fixture.home_team_id
            and fixture.away_team_id
            and fixture.state != "cancelled"
        )
        if not fixtures:
            raise ValidationError(_("Generate competition fixtures before scheduling."))
        return fixtures

    def _capacities(self):
        capacities = []
        generator = self.env["federation.slot.generator"]
        for day in self.matchday_ids.sorted(lambda item: (item.date, item.id)):
            plan = generator.plan(
                day,
                day.planning_court_ids,
                day.default_day_start_hour,
                day.default_day_end_hour,
                day.default_slot_duration_minutes,
                noon_pause=day.default_noon_pause,
                noon_pause_minutes=day.default_noon_pause_minutes,
            )
            capacities.append(
                {
                    "matchday_id": day.id,
                    "date": day.date,
                    "capacity": len(plan["available"]),
                    "blocked": plan["blocked_count"],
                }
            )
        return capacities

    def _proposal(self):
        fixtures = self._fixtures()
        capacities = self._capacities()
        distribution = self.env[
            "federation.competition.schedule.distributor"
        ].distribute(fixtures, capacities)
        return fixtures, capacities, distribution

    def action_preview(self):
        self._validate_inputs()
        fixtures, capacities, distribution = self._proposal()
        deferred = self.structure_ids.mapped("fixture_ids") - fixtures
        self.write(
            {
                "preview_ready": True,
                "preview_report": json.dumps(
                    {
                        "fixture_count": len(fixtures),
                        "deferred_fixture_count": len(deferred),
                        "available_slot_count": sum(
                            day["capacity"] for day in capacities
                        ),
                        "game_days": capacities,
                        "planned_fixture_counts": {
                            str(day_id): len(ids)
                            for day_id, ids in distribution["assignments"].items()
                        },
                    },
                    indent=2,
                    default=str,
                ),
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
        self._validate_inputs()
        _fixtures, _capacities, distribution = self._proposal()
        slot_generator = self.env["federation.slot.generator"]
        for day in self.matchday_ids.sorted(lambda item: (item.date, item.id)):
            fixture_ids = distribution["assignments"].get(day.id, [])
            if not fixture_ids:
                continue
            slot_generator.generate_plan(
                day,
                day.planning_court_ids,
                day.default_day_start_hour,
                day.default_day_end_hour,
                day.default_slot_duration_minutes,
                noon_pause=day.default_noon_pause,
                noon_pause_minutes=day.default_noon_pause_minutes,
            )
            fixtures = self.env["federation.fixture"].browse(fixture_ids)
            for structure in fixtures.mapped("structure_id"):
                allocated = fixtures.filtered(
                    lambda fixture: fixture.structure_id == structure
                )
                self.env["federation.matchday.allocation"].create(
                    {
                        "matchday_id": day.id,
                        "structure_id": structure.id,
                        "manual_fixture_ids": [(6, 0, allocated.ids)],
                    }
                )
            day.action_capacity_ready()
            schedule = self.env["federation.schedule"].create(
                {
                    "name": _("%s schedule") % day.display_name,
                    "edition_id": self.edition_id.id,
                    "structure_id": fixtures[:1].structure_id.id,
                    "matchday_id": day.id,
                    "preferred_rest_minutes": self.preferred_rest_minutes,
                }
            )
            self.env["federation.schedule.auto.wizard"].create(
                {
                    "schedule_id": schedule.id,
                    "preferred_rest_minutes": self.preferred_rest_minutes,
                }
            ).action_apply()
            if schedule.unassigned_fixture_ids:
                raise ValidationError(
                    _("%s still has unscheduled fixtures.") % day.display_name
                )
        return {
            "type": "ir.actions.act_window",
            "res_model": "federation.schedule",
            "view_mode": "list,form",
            "domain": [("edition_id", "=", self.edition_id.id)],
        }
