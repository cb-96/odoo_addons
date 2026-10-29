from datetime import timedelta
import hashlib
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from ..coverage_policy import project
from .assignment import MANAGER

ROLES = ("head", "assistant_1", "assistant_2", "fourth", "table")


class Match(models.Model):
    _inherit = "federation.match"
    coverage_override = fields.Boolean(
        string="Explicit duty requirements", tracking=True
    )
    coverage_head_required = fields.Integer(default=1, tracking=True)
    coverage_assistant_1_required = fields.Integer(default=0, tracking=True)
    coverage_assistant_2_required = fields.Integer(default=0, tracking=True)
    coverage_fourth_required = fields.Integer(default=0, tracking=True)
    coverage_table_required = fields.Integer(default=0, tracking=True)
    coverage_owner_id = fields.Many2one(
        "res.users", string="Coverage coordinator", tracking=True
    )
    coverage_nomination_hours = fields.Integer(
        default=72, string="Nomination lead hours", tracking=True
    )
    coverage_response_hours = fields.Integer(
        default=48, string="Response lead hours", tracking=True
    )
    coverage_kickoff = fields.Datetime(compute="_compute_coverage")
    coverage_nomination_deadline = fields.Datetime(compute="_compute_coverage")
    coverage_response_deadline = fields.Datetime(compute="_compute_coverage")
    coverage_state = fields.Selection(
        [
            ("unchecked", "Not checked"),
            ("not_required", "Not required"),
            ("uncovered", "Uncovered"),
            ("needs_action", "Needs action"),
            ("ready", "Accepted and eligible"),
        ],
        compute="_compute_coverage",
        search="_search_coverage_state",
    )
    coverage_required = fields.Integer(compute="_compute_coverage")
    coverage_assigned = fields.Integer(compute="_compute_coverage")
    coverage_accepted = fields.Integer(compute="_compute_coverage")
    coverage_eligible = fields.Integer(compute="_compute_coverage")
    coverage_present = fields.Integer(compute="_compute_coverage")
    coverage_completed = fields.Integer(compute="_compute_coverage")
    coverage_blockers = fields.Text(compute="_compute_coverage")
    coverage_escalation_signature = fields.Char(readonly=True, copy=False)
    coverage_escalated_on = fields.Datetime(readonly=True, copy=False)

    @api.constrains(
        "coverage_head_required",
        "coverage_assistant_1_required",
        "coverage_assistant_2_required",
        "coverage_fourth_required",
        "coverage_table_required",
        "coverage_nomination_hours",
        "coverage_response_hours",
        "coverage_owner_id",
    )
    def _check_coverage_config(self):
        for m in self:
            if (
                any(m["coverage_" + role + "_required"] < 0 for role in ROLES)
                or min(m.coverage_nomination_hours, m.coverage_response_hours) < 0
            ):
                raise ValidationError(
                    _("Coverage counts and lead hours cannot be negative.")
                )
            if m.coverage_owner_id and (
                not m.coverage_owner_id.active
                or not m.coverage_owner_id.has_group(MANAGER)
            ):
                raise ValidationError(
                    _("The coverage coordinator must be an active federation manager.")
                )

    def write(self, vals):
        if any(k.startswith("coverage_") for k in vals):
            self._coverage_assert_manager()
            if {"coverage_escalation_signature", "coverage_escalated_on"}.intersection(
                vals
            ):
                raise ValidationError(
                    _("Escalation evidence is managed by the coverage command.")
                )
        return super().write(vals)

    def _coverage_assert_manager(self):
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(_("Only federation managers may resolve coverage."))
        self.check_access("write")

    @api.model
    def _coverage_lock_matches(self, matches):
        ids = sorted(matches.ids)
        if ids:
            self.env.cr.execute(
                (
                    "SELECT id FROM federation_match WHERE id IN %s ORDER "
                    "BY id FOR UPDATE"
                ),
                [tuple(ids)],
            )
            matches.invalidate_recordset()

    def _coverage_assert_current(self):
        self.ensure_one()
        p = self.schedule_publication_id
        if (
            not self.logical_fixture_id
            or not p
            or p.state != "live"
            or p.matchday_id.current_publication_id != p
            or self.state in ("done", "cancelled")
        ):
            raise ValidationError(
                _(
                    (
                        "Resolve duties only on an active match in the current "
                        "live schedule."
                    )
                )
            )

    def _coverage_requirements(self):
        self.ensure_one()
        rule = self._get_effective_officiating_rule_set()
        checked = bool(self.coverage_override or rule)
        if self.coverage_override:
            requirements = {
                role: self["coverage_" + role + "_required"] for role in ROLES
            }
        else:
            count = self._get_required_referee_count()
            requirements = {role: int(i < count) for i, role in enumerate(ROLES)}
            if count > len(ROLES):
                checked = False
        for role in ROLES:
            requirements[role] = max(
                requirements[role],
                len(self.club_referee_duty_ids.filtered(lambda d: d.role == role)),
            )
        return requirements, checked

    def _coverage_snapshot(self):
        self.ensure_one()
        requirements, checked = self._coverage_requirements()
        assignments = self.referee_assignment_ids
        assignments._compute_coverage_facts()
        pending = self.club_referee_duty_ids.filtered(
            lambda d: d.state != "confirmed"
            or not d.assignment_id
            or d.assignment_id.state == "cancelled"
            or not d.assignment_id.coverage_accepted
            or not d.assignment_id.coverage_eligible
        )
        rows = [
            dict(
                role=a.role,
                active=a.state != "cancelled",
                accepted=a.coverage_accepted,
                eligible=a.coverage_eligible,
                present=a.coverage_present,
                completed=a.state == "done",
            )
            for a in assignments
        ]
        snapshot = project(requirements, rows, len(pending), checked)
        if snapshot["state"] == "ready" and any(
            a.state != "cancelled"
            and (not a.coverage_accepted or not a.coverage_eligible)
            for a in assignments
        ):
            snapshot["state"] = "needs_action"
        pub = self.schedule_publication_id
        if (
            self.state == "cancelled"
            or not pub
            or pub.state != "live"
            or pub.matchday_id.current_publication_id != pub
        ):
            snapshot["state"] = "unchecked"
        blockers = []
        if not checked:
            blockers.append(
                _("Duty requirements are not checked; configure explicit counts.")
            )
        if snapshot["state"] == "unchecked":
            blockers.append(_("Schedule or duty requirements are not checked."))
        for role, missing in snapshot["missing"].items():
            if missing:
                blockers.append(
                    _(
                        "%(count)s %(role)s assignment(s) missing.",
                        count=missing,
                        role=role,
                    )
                )
        for d in pending:
            blockers.append(
                _(
                    "Club %(club)s: %(state)s.",
                    club=d.club_id.display_name,
                    state=d.state,
                )
            )
        for a in assignments.filtered(lambda a: a.state != "cancelled"):
            if a.coverage_feedback:
                blockers.append(
                    "%s: %s" % (a.referee_id.display_name, a.coverage_feedback)
                )
        if not self.coverage_owner_id:
            blockers.append(_("Assign a coverage coordinator for escalation."))
        snapshot["blockers"] = "\n".join(blockers)
        return snapshot

    @api.depends(
        "date_scheduled",
        "state",
        "schedule_publication_id",
        "coverage_override",
        "coverage_head_required",
        "coverage_assistant_1_required",
        "coverage_assistant_2_required",
        "coverage_fourth_required",
        "coverage_table_required",
        "coverage_nomination_hours",
        "coverage_response_hours",
        "coverage_owner_id",
        "referee_assignment_ids.coverage_accepted",
        "referee_assignment_ids.coverage_eligible",
        "referee_assignment_ids.coverage_present",
        "schedule_publication_id.state",
        "schedule_publication_id.matchday_id.current_publication_id",
        "operational_slot_id.start_datetime",
        "published_slot_id.start_datetime",
        "tournament_id.rule_set_id.referee_required_count",
        "tournament_id.competition_id.rule_set_id.referee_required_count",
        "referee_assignment_ids.state",
        "referee_assignment_ids.accepted_on",
        "referee_assignment_ids.present_on",
        "club_referee_duty_ids.state",
        "club_referee_duty_ids.assignment_id",
    )
    def _compute_coverage(self):
        for m in self:
            snapshot = m._coverage_snapshot()
            m.coverage_state = snapshot["state"]
            for key in (
                "required",
                "assigned",
                "accepted",
                "eligible",
                "present",
                "completed",
            ):
                m["coverage_" + key] = snapshot[key]
            m.coverage_blockers = snapshot["blockers"]
            slot = m.operational_slot_id or m.published_slot_id
            kickoff = fields.Datetime.to_datetime(
                slot.start_datetime if slot else m.date_scheduled
            )
            m.coverage_kickoff = kickoff
            m.coverage_nomination_deadline = (
                kickoff - timedelta(hours=m.coverage_nomination_hours)
                if kickoff
                else False
            )
            m.coverage_response_deadline = (
                kickoff - timedelta(hours=m.coverage_response_hours)
                if kickoff
                else False
            )

    def _search_coverage_state(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            raise ValidationError(_("Unsupported coverage filter."))
        wanted = set(value if isinstance(value, (list, tuple)) else [value])
        ids = [
            m.id for m in self.search([]) if m._coverage_snapshot()["state"] in wanted
        ]
        return [("id", "not in" if operator in ("!=", "not in") else "in", ids)]

    def action_open_coverage(self):
        self.ensure_one()
        self._coverage_assert_manager()
        return {
            "type": "ir.actions.act_window",
            "name": _("Duty coverage"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref("sports_federation_duty_coverage.coverage_form").id,
                    "form",
                )
            ],
            "target": "current",
        }

    def action_resolve_coverage(self):
        self.ensure_one()
        self._coverage_assert_manager()
        self._coverage_assert_current()
        return {
            "type": "ir.actions.act_window",
            "name": _("Resolve duty coverage"),
            "res_model": "federation.coverage.resolve.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_match_id": self.id},
        }

    def action_refresh_coverage(self):
        self._coverage_assert_manager()
        self.invalidate_recordset()
        self._coverage_sync_escalations()
        return {"type": "ir.actions.client", "tag": "reload"}

    def _coverage_sync_escalations(self):
        activity_type = self.env.ref(
            "sports_federation_duty_coverage.coverage_activity_type"
        )
        for m in self:
            m._coverage_lock_matches(m)
            snapshot = m._coverage_snapshot()
            activities = m.activity_ids.filtered(
                lambda a: a.activity_type_id == activity_type
            )
            now = fields.Datetime.now()
            slot = m.operational_slot_id or m.published_slot_id
            kickoff = fields.Datetime.to_datetime(
                slot.start_datetime if slot else m.date_scheduled
            )
            due = bool(
                kickoff and now >= kickoff - timedelta(hours=m.coverage_response_hours)
            )
            nomination_due = bool(
                kickoff
                and now >= kickoff - timedelta(hours=m.coverage_nomination_hours)
                and m.club_referee_duty_ids.filtered(
                    lambda d: d.state in ("draft", "open", "rejected")
                )
            )
            publication = m.schedule_publication_id
            current = bool(
                publication
                and publication.state == "live"
                and publication.matchday_id.current_publication_id == publication
            )
            missing_presence = bool(
                kickoff
                and now >= kickoff
                and snapshot["present"] < snapshot["required"]
            )
            if missing_presence:
                snapshot["blockers"] += "\n" + _(
                    "Required attendance is not recorded at kickoff."
                )
            unresolved = (
                snapshot["state"] not in ("ready", "not_required") or missing_presence
            )
            if (
                not current
                or m.state in ("done", "cancelled")
                or not unresolved
                or not (due or nomination_due)
            ):
                activities.unlink()
                super(Match, m).write({"coverage_escalation_signature": False})
                continue
            owner = m.coverage_owner_id
            if not owner or not owner.active:
                continue
            signature = hashlib.sha256(
                (snapshot["blockers"] + str(owner.id)).encode()
            ).hexdigest()
            if signature == m.coverage_escalation_signature and activities:
                continue
            activities.unlink()
            m.activity_schedule(
                "sports_federation_duty_coverage.coverage_activity_type",
                user_id=owner.id,
                date_deadline=fields.Date.context_today(m),
                summary=_("Resolve overdue duty coverage"),
                note=snapshot["blockers"],
            )
            super(Match, m).write(
                {
                    "coverage_escalation_signature": signature,
                    "coverage_escalated_on": now,
                }
            )

    @api.model
    def cron_escalate_coverage(self):
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(_("Manager access required."))
        matches = self.search(
            [
                "|",
                ("coverage_escalation_signature", "!=", False),
                "&",
                ("state", "not in", ["done", "cancelled"]),
                ("schedule_publication_id", "!=", False),
            ],
            order="id",
        )
        matches._coverage_sync_escalations()
        return len(matches)

    def _get_officiating_issues(self):
        issues = super()._get_officiating_issues()
        for m in self:
            if m._coverage_snapshot()["state"] not in ("ready", "not_required"):
                issues.append(
                    _(
                        "Coverage requires current individual acceptance "
                        "and eligibility."
                    )
                )
        return issues


class Matchday(models.Model):
    _inherit = "federation.matchday"

    def action_open_duty_coverage(self):
        self.ensure_one()
        self.check_access("read")
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(_("Manager access required."))
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_duty_coverage.coverage_action"
        )
        action["domain"] = [("schedule_publication_id.matchday_id", "=", self.id)]
        return action


class Edition(models.Model):
    _inherit = "federation.competition.edition"

    def action_open_duty_coverage(self):
        self.ensure_one()
        self.check_access("read")
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(_("Manager access required."))
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_duty_coverage.coverage_action"
        )
        action["domain"] = [("tournament_id.edition_id", "=", self.id)]
        return action
