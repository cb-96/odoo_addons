from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError
from .assignment import MANAGER


class Duty(models.Model):
    _inherit = "federation.match.club.referee.duty"
    coverage_deadline = fields.Datetime(compute="_compute_coverage_deadline")
    coverage_feedback = fields.Text(compute="_compute_coverage_deadline")

    def _compute_coverage_deadline(self):
        for d in self:
            d.coverage_deadline = d.match_id.coverage_nomination_deadline
            if d.state in ("draft", "open", "rejected"):
                d.coverage_feedback = _("Club nomination is outstanding.")
            elif d.state == "nominated":
                d.coverage_feedback = _("Coordinator must link the nominated official.")
            elif not d.assignment_id or d.assignment_id.state == "cancelled":
                d.coverage_feedback = _(
                    "Assignment is missing or cancelled; replacement is required."
                )
            else:
                d.coverage_feedback = d.assignment_id.coverage_feedback

    def _coverage_lock_duties(self):
        self.env["federation.match"]._coverage_lock_matches(self.mapped("match_id"))
        if self.ids:
            self.env.cr.execute(
                (
                    "SELECT id FROM federation_match_club_referee_duty "
                    "WHERE id IN %s ORDER BY id FOR UPDATE"
                ),
                [tuple(sorted(self.ids))],
            )
            self.invalidate_recordset()

    def _coverage_assert_manager(self):
        if self.env.uid != 1 and not self.env.user.has_group(MANAGER):
            raise AccessError(
                _("Only federation managers may confirm or reopen duties.")
            )
        self.check_access("write")

    def write(self, vals):
        if {
            "state",
            "assignment_id",
            "nominated_player_id",
            "nominated_by_id",
            "nominated_on",
            "club_id",
            "match_id",
            "role",
        }.intersection(vals):
            self._coverage_assert_manager()
            self._coverage_lock_duties()
        return super().write(vals)

    def unlink(self):
        raise ValidationError(_("Keep club-duty history; do not delete duty records."))

    def action_open(self):
        self._coverage_assert_manager()
        self._coverage_lock_duties()
        return super().action_open()

    def action_nominate(self, player_id):
        self._coverage_lock_duties()
        manager = self.env.uid == 1 or self.env.user.has_group(MANAGER)
        for d in self:
            if not manager and d.club_id not in self.env.user.portal_club_scope_ids:
                raise AccessError(
                    _("This duty is outside your current club responsibility.")
                )
            d.check_access("write")
            d.match_id._coverage_assert_current()
            if d.state not in ("open", "rejected"):
                if d.state == "nominated" and d.nominated_player_id.id == int(
                    player_id
                ):
                    continue
                raise ValidationError(_("This duty is no longer open for nomination."))
            player = self.env["federation.player"].browse(int(player_id)).exists()
            if not player or player.club_id != d.club_id:
                raise ValidationError(
                    _("Nominate a player belonging to the responsible club.")
                )
            super(Duty, d).write(
                {
                    "state": "nominated",
                    "nominated_player_id": player.id,
                    "nominated_by_id": self.env.user.id,
                    "nominated_on": fields.Datetime.now(),
                }
            )
        return True

    def _get_or_create_referee_for_player(self, player):
        self._coverage_assert_manager()
        model = self.env["federation.referee"]
        referee = model.search([("coverage_player_id", "=", player.id)], limit=1)
        if not referee:
            referee = model.create(
                {"name": player.display_name, "coverage_player_id": player.id}
            )
        return referee

    def action_confirm(self):
        self._coverage_assert_manager()
        self._coverage_lock_duties()
        for d in self:
            d.match_id._coverage_assert_current()
            if (
                d.state == "confirmed"
                and d.assignment_id
                and d.assignment_id.state != "cancelled"
            ):
                continue
            if d.state != "nominated" or not d.nominated_player_id:
                raise ValidationError(
                    _("Nominate a player before linking the assignment.")
                )
            referee = d._get_or_create_referee_for_player(d.nominated_player_id)
            model = self.env["federation.match.referee"]
            assignment = model.search(
                [
                    ("match_id", "=", d.match_id.id),
                    ("referee_id", "=", referee.id),
                    ("role", "=", d.role),
                    ("state", "!=", "cancelled"),
                ],
                limit=1,
            )
            if not assignment:
                assignment = model.create(
                    {
                        "match_id": d.match_id.id,
                        "referee_id": referee.id,
                        "role": d.role,
                        "state": "draft",
                    }
                )
            # Coordinator linkage is deliberately not individual acceptance.
            super(Duty, d).write({"state": "confirmed", "assignment_id": assignment.id})
        return True

    def action_reject(self, reason=""):
        self._coverage_assert_manager()
        self._coverage_lock_duties()
        if not reason.strip():
            raise ValidationError(_("Record a rejection reason."))
        return super().action_reject(reason=reason)

    def action_cancel(self):
        self._coverage_assert_manager()
        self._coverage_lock_duties()
        return super().action_cancel()

    def action_coverage_reopen(self):
        self._coverage_assert_manager()
        self._coverage_lock_duties()
        for d in self:
            if d.assignment_id and d.assignment_id.state != "cancelled":
                raise ValidationError(
                    _(
                        (
                            "Replace or cancel the active assignment before "
                            "reopening nomination."
                        )
                    )
                )
            super(Duty, d).write({"state": "rejected"})
        return True

    def _compute_nomination_deadline(self):
        for d in self:
            d.nomination_deadline = d.match_id.coverage_nomination_deadline
