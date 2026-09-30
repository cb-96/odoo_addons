from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sports_federation_base.destructive_tokens import (
    MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY,
    MATCHDAY_DESTRUCTIVE_DELETE_TOKEN,
)


class FederationScheduleIntegrity(models.Model):
    _inherit = "federation.schedule"

    amendment_impact = fields.Text(compute="_compute_amendment_impact")

    @api.depends("supersedes_id", "assignment_ids.slot_id",
                 "supersedes_id.assignment_ids.slot_id")
    def _compute_amendment_impact(self):
        for schedule in self:
            if not schedule.supersedes_id:
                schedule.amendment_impact = False
                continue
            before = {a.fixture_id.id: a.slot_id for a in schedule.supersedes_id.assignment_ids}
            after = {a.fixture_id.id: a.slot_id for a in schedule.assignment_ids}
            moved = sorted(fid for fid in before.keys() & after.keys()
                           if before[fid].id != after[fid].id)
            added = sorted(after.keys() - before.keys())
            removed = sorted(before.keys() - after.keys())
            summary = _("Compared with the original schedule: %(moved)s moved, "
                        "%(added)s added, %(removed)s removed. "
                        "The live publication remains unchanged until approval and publication.",
                        moved=len(moved), added=len(added), removed=len(removed))
            fixtures = self.env["federation.fixture"]
            details = [_("%(fixture)s: %(old)s -> %(new)s",
                         fixture=fixtures.browse(fid).display_name,
                         old=before[fid].display_name, new=after[fid].display_name)
                       for fid in moved[:5]]
            details += [_("Added: %s", fixtures.browse(fid).display_name)
                        for fid in added[:5]]
            details += [_("Removed: %s", fixtures.browse(fid).display_name)
                        for fid in removed[:5]]
            schedule.amendment_impact = "\n".join([summary] + details)

    _MUTABLE_STATES = ("draft", "changes_requested")
    _PROTECTED_FIELDS = {"edition_id", "structure_id", "matchday_id", "assignment_ids"}

    @api.constrains("matchday_id", "state")
    def _check_one_active_schedule(self):
        for record in self.filtered(lambda item: item.state != "superseded"):
            duplicate = self.search_count(
                [
                    ("matchday_id", "=", record.matchday_id.id),
                    ("state", "!=", "superseded"),
                    ("id", "!=", record.id),
                ]
            )
            if duplicate:
                raise ValidationError(
                    "A match day can have only one active working schedule."
                )

    def action_create_revision(self, reason):
        self.ensure_one()
        if self.state != "published":
            raise ValidationError(
                "Only a published schedule can start a replacement revision."
            )
        if self.matchday_id.state == "open":
            raise ValidationError(
                "Close live match-day operations before replacing its schedule."
            )
        if not (reason or "").strip():
            raise ValidationError(
                "Explain why the published schedule must be replaced."
            )
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id, "schedule_planner", "competition_director"
        )
        self.env.cr.execute(
            "SELECT id FROM federation_schedule WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset(["state", "superseded_by_id"])
        if self.state != "published":
            raise ValidationError(
                _("Only the current published schedule can be amended.")
            )
        if self.superseded_by_id:
            raise ValidationError(
                _("A replacement revision already exists for this schedule.")
            )
        self.state = "superseded"
        replacement = self.copy(
            {
                "name": f"{self.name} revision",
                "state": "changes_requested",
                "revision": 0,
                "supersedes_id": self.id,
                "revision_reason": reason,
                "change_ids": False,
            }
        )
        if self.assignment_ids:
            self.env["federation.schedule.assignment"].create(
                [
                    {
                        "schedule_id": replacement.id,
                        "fixture_id": assignment.fixture_id.id,
                        "slot_id": assignment.slot_id.id,
                        "method": assignment.method,
                        "assigned_by_id": assignment.assigned_by_id.id,
                    }
                    for assignment in self.assignment_ids
                ]
            )
        self.superseded_by_id = replacement.id
        return replacement

    def assert_mutable(self):
        if self.filtered(lambda record: record.state not in self._MUTABLE_STATES):
            raise ValidationError(
                "Submitted, approved and published schedules are immutable."
            )
        return True

    def write(self, vals):
        if self._PROTECTED_FIELDS.intersection(vals):
            self.assert_mutable()
        return super().write(vals)

    def unlink(self):
        if (
            self.env.context.get(MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY)
            is MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
        ):
            return super().unlink()
        self.assert_mutable()
        return super().unlink()


class FederationScheduleAssignmentIntegrity(models.Model):
    _inherit = "federation.schedule.assignment"

    @api.model_create_multi
    def create(self, vals_list):
        self.env["federation.schedule"].browse(
            [vals["schedule_id"] for vals in vals_list if vals.get("schedule_id")]
        ).assert_mutable()
        return super().create(vals_list)

    def write(self, vals):
        self.mapped("schedule_id").assert_mutable()
        return super().write(vals)

    def unlink(self):
        self.mapped("schedule_id").assert_mutable()
        return super().unlink()
