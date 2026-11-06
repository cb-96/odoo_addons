import hashlib
import json
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from ..models.assignment import Assignment
from ..models.duty import Duty


class Resolve(models.TransientModel):
    _name = "federation.coverage.resolve.wizard"
    _description = "Resolve schedule-linked duty coverage"
    match_id = fields.Many2one("federation.match", required=True)
    operation = fields.Selection(
        [
            ("assign", "Assign official"),
            ("club", "Request club nomination"),
            ("link", "Link nominated duty"),
            ("reopen", "Reopen club nomination"),
            ("replace", "Replace assignment"),
        ],
        default="assign",
        required=True,
    )
    selected_role = fields.Selection(
        [
            ("head", "Head"),
            ("assistant_1", "Assistant 1"),
            ("assistant_2", "Assistant 2"),
            ("fourth", "Fourth"),
            ("table", "Table"),
        ],
        default="head",
        required=True,
    )
    referee_id = fields.Many2one("federation.referee")
    club_id = fields.Many2one("federation.club")
    duty_id = fields.Many2one("federation.match.club.referee.duty")
    assignment_id = fields.Many2one("federation.match.referee")
    reason = fields.Text()
    expected_signature = fields.Char(readonly=True)
    result_assignment_id = fields.Many2one(
        "federation.match.referee", readonly=True, copy=False
    )
    applied = fields.Boolean(readonly=True, copy=False)
    preview = fields.Text(compute="_compute_preview")

    def _signature(self):
        self.ensure_one()
        m = self.match_id
        assignments = m.referee_assignment_ids.sorted("id")
        duties = m.club_referee_duty_ids.sorted("id")
        payload = [
            m.id,
            str(m.date_scheduled),
            m.schedule_publication_id.id,
            m.schedule_publication_id.matchday_id.current_publication_id.id,
            m.schedule_publication_id.state,
            m.operational_slot_id.id,
            str(m.operational_slot_id.write_date),
            m.published_slot_id.id,
            str(m.published_slot_id.write_date),
            m._coverage_requirements(),
            [
                (a.id, a.state, a.referee_id.id, a.role, str(a.write_date))
                for a in assignments
            ],
            [(d.id, d.state, d.assignment_id.id, str(d.write_date)) for d in duties],
        ]
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()

    @api.model
    def default_get(self, names):
        vals = super().default_get(names)
        if vals.get("match_id"):
            probe = self.new(vals)
            probe.match_id._coverage_assert_manager()
            vals["expected_signature"] = probe._signature()
        return vals

    @api.onchange("match_id")
    def _onchange_match(self):
        if self.match_id:
            self.match_id._coverage_assert_manager()
            self.expected_signature = self._signature()

    @api.depends(
        "match_id", "referee_id", "selected_role", "assignment_id", "operation"
    )
    def _compute_preview(self):
        for w in self:
            if not w.match_id:
                w.preview = False
                continue
            w.match_id._coverage_assert_manager()
            text = w.match_id._coverage_snapshot()["blockers"]
            if w.referee_id:
                probe = w.env["federation.match.referee"].new(
                    {
                        "match_id": w.match_id.id,
                        "referee_id": w.referee_id.id,
                        "role": (
                            w.assignment_id.role
                            if w.operation == "replace"
                            else w.selected_role
                        ),
                    }
                )
                text += "\nCandidate: " + "\n".join(probe._coverage_issues())
            w.preview = text or _(
                (
                    "No coverage blockers. Individual acceptance is still "
                    "required for new assignments."
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get("applied") or v.get("result_assignment_id") for v in vals_list):
            raise ValidationError(
                _("Result evidence cannot be supplied by the caller.")
            )
        return super().create(vals_list)

    def write(self, vals):
        if {"applied", "result_assignment_id"}.intersection(vals):
            raise ValidationError(
                _("Result evidence is managed by the resolution command.")
            )
        if self.filtered("applied"):
            raise ValidationError(_("An applied resolution cannot be edited."))
        return super().write(vals)

    def action_apply(self):
        self.ensure_one()
        m = self.match_id
        m._coverage_assert_manager()
        m._coverage_lock_matches(m)
        self.env.cr.execute(
            (
                "SELECT id FROM federation_coverage_resolve_wizard "
                "WHERE id=%s FOR UPDATE"
            ),
            [self.id],
        )
        self.invalidate_recordset()
        if self.applied:
            return m.action_open_coverage()
        m._coverage_assert_current()
        if not self.expected_signature or self.expected_signature != self._signature():
            raise ValidationError(
                _(
                    (
                        "Coverage changed since this preview. Close and reopen "
                        "the resolution."
                    )
                )
            )
        if self.duty_id and self.duty_id.match_id != m:
            raise ValidationError(_("Duty belongs to another match."))
        if self.assignment_id and self.assignment_id.match_id != m:
            raise ValidationError(_("Assignment belongs to another match."))
        refs = sorted(set((self.referee_id | self.assignment_id.referee_id).ids))
        if refs:
            self.env.cr.execute(
                (
                    "SELECT id FROM federation_referee WHERE id IN %s ORDER "
                    "BY id FOR UPDATE"
                ),
                [tuple(refs)],
            )
        result = self.env["federation.match.referee"]
        with self.env.cr.savepoint():
            if self.operation in ("assign", "replace"):
                if not self.referee_id:
                    raise ValidationError(_("Choose an official."))
                old = self.assignment_id if self.operation == "replace" else result
                if self.operation == "replace" and (
                    not old or old.state == "done" or old.replacement_ids
                ):
                    raise ValidationError(
                        _("Choose an unreplaced assignment that is not completed.")
                    )
                if old and (
                    not (self.reason or "").strip() or old.referee_id == self.referee_id
                ):
                    raise ValidationError(
                        _("Replacement needs a different official and a reason.")
                    )
                role = old.role if old else self.selected_role
                probe = result.new(
                    {"match_id": m.id, "referee_id": self.referee_id.id, "role": role}
                )
                issues = probe._coverage_issues()
                if issues:
                    raise ValidationError("\n".join(issues))
                linked = m.club_referee_duty_ids.filtered(
                    lambda d: old and d.assignment_id == old
                )
                for duty in linked:
                    if (
                        not self.referee_id.coverage_player_id
                        or self.referee_id.coverage_player_id.club_id != duty.club_id
                    ):
                        raise ValidationError(
                            _(
                                (
                                    "Replace a club duty with a linked player "
                                    "from that "
                                    "club, or reopen nomination."
                                )
                            )
                        )
                existing = result.search(
                    [
                        ("match_id", "=", m.id),
                        ("referee_id", "=", self.referee_id.id),
                        ("role", "=", role),
                        ("state", "!=", "cancelled"),
                    ],
                    limit=1,
                )
                if old and existing:
                    raise ValidationError(_("Replacement already has this duty."))
                result = existing or result.create(
                    {
                        "match_id": m.id,
                        "referee_id": self.referee_id.id,
                        "role": role,
                        "state": "draft",
                    }
                )
                if old:
                    old.action_cancel()
                    super(Assignment, result).write(
                        {
                            "replaces_id": old.id,
                            "replacement_reason": self.reason.strip(),
                        }
                    )
                    nominee = self.referee_id.coverage_player_id
                    for duty in linked:
                        super(Duty, duty).write(
                            {
                                "assignment_id": result.id,
                                "state": "confirmed",
                                "nominated_player_id": nominee.id,
                            }
                        )
                    old.message_post(
                        body=_(
                            "Replaced by assignment %(id)s. Reason: %(reason)s",
                            id=result.id,
                            reason=self.reason.strip(),
                        )
                    )
            elif self.operation == "club":
                if not self.club_id:
                    raise ValidationError(_("Choose the responsible club."))
                duty = self.env["federation.match.club.referee.duty"].search(
                    [
                        ("match_id", "=", m.id),
                        ("club_id", "=", self.club_id.id),
                        ("role", "=", self.selected_role),
                    ],
                    limit=1,
                )
                if not duty:
                    duty = self.env["federation.match.club.referee.duty"].create(
                        {
                            "match_id": m.id,
                            "club_id": self.club_id.id,
                            "role": self.selected_role,
                        }
                    )
                if duty.state == "draft":
                    duty.action_open()
            elif self.operation == "link":
                if not self.duty_id:
                    raise ValidationError(_("Choose the nominated duty."))
                self.duty_id.action_confirm()
                result = self.duty_id.assignment_id
            elif self.operation == "reopen":
                if not self.duty_id or not (self.reason or "").strip():
                    raise ValidationError(_("Choose a duty and record a reason."))
                self.duty_id.action_coverage_reopen()
                self.duty_id.message_post(body=self.reason.strip())
            super().write({"applied": True, "result_assignment_id": result.id})
            m._coverage_sync_escalations()
        return m.action_open_coverage()
