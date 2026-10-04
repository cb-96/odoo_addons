from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationCompetitionEntry(models.Model):
    _inherit = "federation.competition.entry"

    @api.model
    def _portal_open_window_for_division(self, division, window=None, user=None):
        privilege = self.env["federation.portal.privilege"]
        division = privilege.elevate(division, user=user)
        if window:
            window = privilege.elevate(window, user=user)
            now = fields.Datetime.now()
            if (
                not window.exists()
                or window.division_id != division
                or window.edition_id != division.edition_id
                or window.state != "open"
                or (window.date_open and window.date_open > now)
                or (window.date_close and window.date_close < now)
            ):
                raise ValidationError(
                    _("The selected registration window is not currently open for this division.")
                )
            return window
        now = fields.Datetime.now()
        return (
            self.env["federation.registration.window"]
            .sudo()
            .search(
                [
                    ("division_id", "=", division.id),
                    ("edition_id", "=", division.edition_id.id),
                    ("state", "=", "open"),
                    "|",
                    ("date_open", "=", False),
                    ("date_open", "<=", now),
                    "|",
                    ("date_close", "=", False),
                    ("date_close", ">=", now),
                ],
                order="date_close asc, id desc",
                limit=1,
            )
        )

    @api.model
    def _portal_validate_submission(
        self, division, team, window=None, exclude_entry=None, user=None
    ):
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        division = privilege.elevate(division, user=user)
        team = privilege.elevate(team, user=user)
        if not division.exists() or not division.edition_id:
            raise ValidationError(_("Select a valid competition division."))
        window = self._portal_open_window_for_division(
            division, window=window, user=user
        )
        if not window:
            raise ValidationError(_("Registration is not open for this division."))
        self.env["federation.portal.scope"].assert_team(team, user=user)
        error = division.get_team_eligibility_error(team)
        if error:
            raise ValidationError(error)
        duplicate_domain = [
            ("window_id", "=", window.id),
            ("team_id", "=", team.id),
            ("state", "!=", "withdrawn"),
        ]
        if exclude_entry:
            duplicate_domain.append(("id", "!=", exclude_entry.id))
        if self.sudo().search(duplicate_domain, limit=1):
            raise ValidationError(_("This team already has an active entry."))
        if (
            division.max_participants > 0
            and self.sudo().search_count(
                [
                    ("window_id", "=", window.id),
                    ("state", "in", ("submitted", "approved")),
                ]
            )
            >= division.max_participants
        ):
            raise ValidationError(_("This division has reached its entry capacity."))

        return window

    @api.model
    def _portal_submit_entry(self, division, team, notes=None, user=None, window=None):
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        division = privilege.elevate(division, user=user)
        team = privilege.elevate(team, user=user)
        window = self._portal_validate_submission(
            division, team, window=window, user=user
        )
        existing = self.sudo().search(
            [("window_id", "=", window.id), ("team_id", "=", team.id)],
            limit=1,
        )
        submission_note = (notes or "").strip() or False
        scope_domain = [("window_id", "=", window.id), ("team_id", "=", team.id)]
        if existing and existing.state == "withdrawn":
            privilege.portal_write(
                existing,
                {"submission_note": submission_note},
                scope_domain=scope_domain,
                user=user,
            )
            privilege.portal_call(
                existing, "action_submit", scope_domain=scope_domain, user=user
            )
            return existing

        entry = privilege.portal_create(
            self,
            {
                "window_id": window.id,
                "team_id": team.id,
                "submission_note": submission_note,
                "submitted_by_id": user.id,
            },
            user=user,
        )
        privilege.portal_call(
            entry,
            "action_submit",
            scope_domain=scope_domain,
            user=user,
        )
        return entry

    def portal_resubmit(self, notes=None, user=None):
        self.ensure_one()
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        entry = privilege.elevate(self, user=user)
        self.env["federation.portal.scope"].assert_team(entry.team_id, user=user)
        if entry.state not in ("draft", "rejected", "withdrawn"):
            raise ValidationError(
                _("Only draft, returned, rejected, or withdrawn entries can be resubmitted.")
            )
        self._portal_validate_submission(
            entry.window_id.division_id,
            entry.team_id,
            window=entry.window_id,
            exclude_entry=entry,
            user=user,
        )
        scope_domain = [
            ("window_id", "=", entry.window_id.id),
            ("team_id", "=", entry.team_id.id),
        ]
        privilege.portal_write(
            entry,
            {"submission_note": (notes or "").strip() or False},
            scope_domain=scope_domain,
            user=user,
        )
        privilege.portal_call(
            entry, "action_submit", scope_domain=scope_domain, user=user
        )
        return True

    def portal_withdraw(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        entry = privilege.elevate(self, user=user)
        self.env["federation.portal.scope"].assert_team(entry.team_id, user=user)
        scope_domain = [
            ("window_id", "=", entry.window_id.id),
            ("team_id", "=", entry.team_id.id),
        ]
        return privilege.portal_call(
            entry, "action_withdraw", scope_domain=scope_domain, user=user
        )

    def get_portal_state_label(self):
        self.ensure_one()
        if self.state == "draft" and self.review_note:
            return _("Returned for updates")
        return {
            "draft": _("Draft"),
            "submitted": _("Awaiting federation review"),
            "approved": _("Approved"),
            "rejected": _("Rejected"),
            "withdrawn": _("Withdrawn"),
        }.get(self.state, self.state or "")
