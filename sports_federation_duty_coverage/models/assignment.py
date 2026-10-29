import hashlib
import json
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

MANAGER = "sports_federation_base.group_federation_manager"
PROTECTED = {
    "state",
    "accepted_on",
    "accepted_by_id",
    "accepted_signature",
    "present_on",
    "present_by_id",
    "replaces_id",
    "replacement_reason",
    "confirmed_on",
    "completed_on",
    "cancelled_on",
    "referee_id",
    "match_id",
    "role",
}


class Referee(models.Model):
    _inherit = "federation.referee"
    coverage_playing_checked = fields.Boolean(
        string="Playing commitments checked", tracking=True
    )
    coverage_player_id = fields.Many2one(
        "federation.player",
        ondelete="restrict",
        tracking=True,
        help=(
            "Explicit player identity used for playing conflicts; "
            "never inferred from a name."
        ),
    )

    def write(self, vals):
        if (
            {"coverage_player_id", "coverage_playing_checked"}.intersection(vals)
            and self.env.uid != 1
            and not self.env.user.has_group(MANAGER)
        ):
            raise AccessError(_("Only managers may link playing identities."))
        return super().write(vals)

    _coverage_player_unique = models.Constraint(
        "UNIQUE(coverage_player_id)",
        "A player can be linked to only one official profile.",
    )


class Assignment(models.Model):
    _inherit = "federation.match.referee"
    state = fields.Selection(tracking=True)
    _match_referee_role_unique = models.Constraint(
        "CHECK (true)",
        "Active assignment uniqueness is enforced by the coverage index.",
    )

    def init(self):
        self.env.cr.execute(
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "federation_coverage_active_assignment_unique ON "
                "federation_match_referee (match_id, referee_id, role) "
                "WHERE state != 'cancelled'"
            )
        )

    accepted_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    accepted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    accepted_signature = fields.Char(readonly=True, copy=False)
    present_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    present_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    replaces_id = fields.Many2one(
        "federation.match.referee", readonly=True, copy=False, ondelete="restrict"
    )
    replacement_ids = fields.One2many(
        "federation.match.referee", "replaces_id", readonly=True
    )
    replacement_reason = fields.Text(readonly=True, copy=False)
    coverage_accepted = fields.Boolean(compute="_compute_coverage_facts")
    coverage_eligible = fields.Boolean(compute="_compute_coverage_facts")
    coverage_present = fields.Boolean(compute="_compute_coverage_facts")
    coverage_feedback = fields.Text(compute="_compute_coverage_facts")

    def _coverage_assert_manager(self):
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(
                _("Only federation managers may change coverage or attendance.")
            )
        self.check_access("write")

    def _coverage_lock(self):
        # Lock matches, then profiles in stable order. Serialize creation/replacement
        # and responses.
        self.env["federation.match"]._coverage_lock_matches(self.mapped("match_id"))
        refs = self.mapped("referee_id").ids
        if refs:
            self.env.cr.execute(
                (
                    "SELECT id FROM federation_referee WHERE id IN %s ORDER "
                    "BY id FOR UPDATE"
                ),
                [tuple(sorted(refs))],
            )
        if self.ids:
            self.env.cr.execute(
                (
                    "SELECT id FROM federation_match_referee WHERE id IN %s "
                    "ORDER BY id FOR UPDATE"
                ),
                [tuple(sorted(self.ids))],
            )
            self.invalidate_recordset()

    def _coverage_signature(self):
        self.ensure_one()
        m = self.match_id
        slot = m.operational_slot_id or m.published_slot_id
        start, end = self._assignment_window()
        values = [
            m.id,
            m.schedule_publication_id.id,
            m.schedule_publication_id.state,
            m.schedule_publication_id.matchday_id.current_publication_id.id,
            slot.id,
            str(start),
            str(end),
            str(m.date_scheduled),
            str(slot.court_id.id if slot and "court_id" in slot._fields else False),
            self.role,
            self.referee_id.id,
        ]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    def _coverage_current(self):
        self.ensure_one()
        pub = self.publication_id
        return bool(
            self.fixture_id
            and pub
            and pub.state == "live"
            and pub.matchday_id.current_publication_id == pub
            and self.match_id.state != "cancelled"
        )

    def _coverage_issues(self):
        self.ensure_one()
        # Privileged read only after access to this assignment; do not leak
        # conflicting records.
        a = self.sudo()
        issues = []
        if not a._coverage_current():
            issues.append(_("Schedule is not the current live publication."))
        if not a.match_id.date_scheduled:
            issues.append(_("Match time is not checked."))
        if not (a.operational_slot_id or a.published_slot_id):
            issues.append(_("Schedule slot and duration are not checked."))
        slot = a.operational_slot_id or a.published_slot_id
        if slot and slot.state != "available":
            issues.append(_("The operational slot is blocked or a break."))
        if not a.referee_id.coverage_playing_checked:
            issues.append(_("Playing commitments are not checked."))
        duplicates = a.search_count(
            [
                ("match_id", "=", a.match_id.id),
                ("referee_id", "=", a.referee_id.id),
                ("state", "!=", "cancelled"),
            ]
        )
        if duplicates > 1:
            issues.append(
                _("The same official is assigned to multiple duties in this match.")
            )
        if not a.referee_id.user_id:
            issues.append(_("Official login is not linked."))
        if not a.referee_id.active:
            issues.append(_("Official is inactive."))
        if not a._has_valid_certification_for_match():
            issues.append(_("Certification is missing or expired."))
        if not a.referee_id.availability_ids.filtered("active"):
            issues.append(_("Availability is not checked. Add an availability window."))
        elif not a._window_is_covered_by_availability():
            issues.append(_("Official is unavailable during this match."))
        if a._get_overlapping_assignments():
            issues.append(_("Another officiating assignment overlaps."))
        player = a.referee_id.coverage_player_id
        if player:
            teams = player.team_ids
            if a.match_id.home_team_id in teams or a.match_id.away_team_id in teams:
                issues.append(_("Official belongs to a team playing this match."))
            start, end = a._assignment_window()
            if start and teams:
                matches = a.env["federation.match"].search(
                    [
                        ("state", "!=", "cancelled"),
                        ("id", "!=", a.match_id.id),
                        "|",
                        ("home_team_id", "in", teams.ids),
                        ("away_team_id", "in", teams.ids),
                    ]
                )
                for match in matches:
                    # Reuse the canonical slot/window calculation without creating a
                    # record.
                    probe = a.new(
                        {
                            "match_id": match.id,
                            "referee_id": a.referee_id.id,
                            "role": a.role,
                        }
                    )
                    if a._windows_overlap(start, end, *probe._assignment_window()):
                        issues.append(_("A playing commitment overlaps this duty."))
                        break
        return issues

    @api.depends(
        "state",
        "role",
        "accepted_on",
        "accepted_signature",
        "present_on",
        "referee_id.active",
        "referee_id.user_id",
        "referee_id.certification_level",
        "referee_id.coverage_playing_checked",
        "referee_id.coverage_player_id.team_ids",
        "referee_id.availability_ids.active",
        "referee_id.availability_ids.date_start",
        "referee_id.availability_ids.date_end",
        "referee_id.certification_ids.active",
        "referee_id.certification_ids.issue_date",
        "referee_id.certification_ids.expiry_date",
        "match_id.date_scheduled",
        "match_id.state",
        "publication_id.state",
        "publication_id.matchday_id.current_publication_id",
        "referee_id.match_assignment_ids.state",
        "referee_id.match_assignment_ids.match_id.date_scheduled",
        "operational_slot_id.start_datetime",
        "operational_slot_id.end_datetime",
        "operational_slot_id.court_id",
        "operational_slot_id.state",
        "published_slot_id.start_datetime",
        "published_slot_id.end_datetime",
        "published_slot_id.court_id",
        "published_slot_id.state",
    )
    def _compute_coverage_facts(self):
        for a in self:
            issues = a._coverage_issues()
            a.coverage_accepted = bool(
                a.state in ("confirmed", "done")
                and a.accepted_on
                and a.accepted_signature == a._coverage_signature()
            )
            a.coverage_eligible = not bool(issues)
            a.coverage_present = bool(
                a.present_on and a.coverage_accepted and a.coverage_eligible
            )
            if a.accepted_on and not a.coverage_accepted and a.state != "cancelled":
                issues.append(
                    _(
                        (
                            "Schedule or assignment changed; individual acceptance "
                            "is required again."
                        )
                    )
                )
            elif not a.accepted_on and a.state != "cancelled":
                issues.append(_("Individual acceptance is outstanding."))
            a.coverage_feedback = "\n".join(issues)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(_("Only federation managers may create assignments."))
        self.env["federation.match"]._coverage_lock_matches(
            self.env["federation.match"].browse(
                [v["match_id"] for v in vals_list if v.get("match_id")]
            )
        )
        refs = sorted({v["referee_id"] for v in vals_list if v.get("referee_id")})
        if refs:
            self.env.cr.execute(
                (
                    "SELECT id FROM federation_referee WHERE id IN %s ORDER "
                    "BY id FOR UPDATE"
                ),
                [tuple(refs)],
            )
        if any(
            v.get("accepted_on") or v.get("accepted_signature") or v.get("present_on")
            for v in vals_list
        ):
            raise ValidationError(
                _(
                    (
                        "Use the acceptance and attendance commands, not "
                        "imported status fields."
                    )
                )
            )
        if any(v.get("state") == "done" or v.get("replaces_id") for v in vals_list):
            raise ValidationError(
                _("Use completion or replacement commands, not imported evidence.")
            )
        records = super().create(vals_list)
        for a in records:
            if a.state != "cancelled" and self.search_count(
                [
                    ("match_id", "=", a.match_id.id),
                    ("referee_id", "=", a.referee_id.id),
                    ("role", "=", a.role),
                    ("state", "!=", "cancelled"),
                    ("id", "!=", a.id),
                ]
            ):
                raise ValidationError(
                    _("This active official/role assignment already exists.")
                )
        return records

    def write(self, vals):
        if {
            "accepted_on",
            "accepted_by_id",
            "accepted_signature",
            "present_on",
            "present_by_id",
            "replaces_id",
            "replacement_reason",
        }.intersection(vals):
            raise ValidationError(_("Use audited commands to change evidence."))
        if PROTECTED.intersection(vals):
            self._coverage_assert_manager()
        if PROTECTED.intersection(vals):
            self._coverage_lock()
        if vals.get("state") == "done" and any(not a.coverage_present for a in self):
            raise ValidationError(
                _("Attendance and current readiness are required for completion.")
            )
        result = super().write(vals)
        if {"referee_id", "match_id", "role", "state"}.intersection(vals):
            for a in self.filtered(lambda x: x.state != "cancelled"):
                if self.search_count(
                    [
                        ("match_id", "=", a.match_id.id),
                        ("referee_id", "=", a.referee_id.id),
                        ("role", "=", a.role),
                        ("state", "!=", "cancelled"),
                        ("id", "!=", a.id),
                    ]
                ):
                    raise ValidationError(
                        _("This active official/role assignment already exists.")
                    )
        return result

    def unlink(self):
        raise ValidationError(
            _("Cancel assignments instead of deleting coverage history.")
        )

    def action_confirm(self):
        self.check_access("read")
        if any(a.referee_id.user_id != self.env.user for a in self):
            raise AccessError(_("Only the assigned individual may accept this duty."))
        self._coverage_lock()
        for a in self:
            if a.referee_id.user_id != self.env.user:
                raise AccessError(
                    _("Only the assigned individual may accept this duty.")
                )
            if a.state not in ("draft", "confirmed"):
                raise ValidationError(
                    _("Only active outstanding assignments can be accepted.")
                )
            if a.coverage_accepted:
                continue
            issues = a._coverage_issues()
            if issues:
                raise ValidationError("\n".join(issues))
            # Explicit command, not a state import, records individual acknowledgement.
            super(Assignment, a).write(
                {
                    "state": "confirmed",
                    "confirmed_on": fields.Datetime.now(),
                    "accepted_on": fields.Datetime.now(),
                    "accepted_by_id": self.env.user.id,
                    "accepted_signature": a._coverage_signature(),
                    "cancelled_on": False,
                    "present_on": False,
                    "present_by_id": False,
                }
            )
        self.mapped("match_id")._coverage_sync_escalations()
        return True

    def action_mark_present(self):
        self._coverage_assert_manager()
        self._coverage_lock()
        for a in self:
            if not a.coverage_accepted or not a.coverage_eligible:
                raise ValidationError(
                    _("Acceptance and eligibility must be current before attendance.")
                )
            if not a.present_on:
                super(Assignment, a).write(
                    {
                        "present_on": fields.Datetime.now(),
                        "present_by_id": self.env.user.id,
                    }
                )
        self.mapped("match_id")._coverage_sync_escalations()
        return True

    def action_clear_presence(self):
        self._coverage_assert_manager()
        self._coverage_lock()
        if self.filtered(lambda a: a.state == "done"):
            raise ValidationError(
                _(
                    (
                        "Completed duties require a reviewed correction, not "
                        "attendance removal."
                    )
                )
            )
        return super().write({"present_on": False, "present_by_id": False})

    def action_done(self):
        self._coverage_assert_manager()
        self._coverage_lock()
        for a in self:
            if a.state == "done":
                continue
            if not a.coverage_present:
                raise ValidationError(
                    _(
                        (
                            "Record current acceptance, eligibility and attendance "
                            "before completion."
                        )
                    )
                )
            super(Assignment, a).action_done()
        self.mapped("match_id")._coverage_sync_escalations()
        return True

    def action_cancel(self):
        self._coverage_assert_manager()
        self._coverage_lock()
        if self.filtered(lambda a: a.state == "done"):
            raise ValidationError(
                _(
                    (
                        "Completed duties cannot be cancelled through the "
                        "ordinary workflow."
                    )
                )
            )
        active = self.filtered(lambda a: a.state != "cancelled")
        if active:
            super(Assignment, active).action_cancel()
        self.mapped("match_id")._coverage_sync_escalations()
        return True

    def action_draft(self):
        self._coverage_assert_manager()
        self._coverage_lock()
        if self.filtered(lambda a: a.state == "done" or a.replacement_ids):
            raise ValidationError(
                _("Completed or replaced assignments cannot be reset.")
            )
        super().action_draft()
        return super().write(
            {
                "accepted_on": False,
                "accepted_by_id": False,
                "accepted_signature": False,
                "present_on": False,
                "present_by_id": False,
            }
        )

    def _portal_action_confirm(self, user=None, response_note=None):
        user = user or self.env.user
        self._portal_assert_access(user=user)
        a = self.with_user(user).sudo()
        a._coverage_lock()
        if response_note:
            super(Assignment, a).write({"response_note": response_note.strip()})
        # Keep the real actor for evidence even though canonical command needs
        # elevation.
        a.action_confirm()
        super(Assignment, a).write({"accepted_by_id": user.id})
        return True

    def _portal_action_decline(self, user=None, response_note=None):
        user = user or self.env.user
        self._portal_assert_access(user=user)
        if not (response_note or "").strip():
            raise ValidationError(_("A decline reason is required."))
        a = self.with_user(user).sudo()
        a._coverage_lock()
        a.match_id._coverage_assert_current()
        if a.filtered(
            lambda x: x.state not in ("draft", "confirmed") or x.coverage_accepted
        ):
            raise ValidationError(
                _(
                    (
                        "Use the coordinator replacement workflow for an "
                        "accepted assignment."
                    )
                )
            )
        super(Assignment, a).write({"response_note": response_note.strip()})
        super(Assignment, a).write(
            {"state": "cancelled", "cancelled_on": fields.Datetime.now()}
        )
        a.match_id._coverage_sync_escalations()
        return True
