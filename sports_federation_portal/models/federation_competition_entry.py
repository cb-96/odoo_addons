from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationCompetitionEntry(models.Model):
    _inherit = "federation.competition.entry"

    @api.model
    def _portal_open_window_for_division(self, division):
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
    def _portal_submit_entry(self, division, team, notes=None, user=None):
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        division = privilege.elevate(division, user=user)
        team = privilege.elevate(team, user=user)
        if not division.exists() or not division.edition_id:
            raise ValidationError(_("Select a valid V2 competition division."))
        window = self._portal_open_window_for_division(division)
        if not window:
            raise ValidationError(_("Registration is not open for this division."))
        clubs = privilege.elevate(
            self.env["federation.club.representative"], user=user
        )._get_clubs_for_user(user=user)
        if team.club_id not in clubs:
            raise AccessError(_("You can only register your own teams."))
        error = division.get_team_eligibility_error(team)
        if error:
            raise ValidationError(error)
        if self.sudo().search(
            [
                ("window_id", "=", window.id),
                ("team_id", "=", team.id),
                ("state", "!=", "withdrawn"),
            ],
            limit=1,
        ):
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
        entry = privilege.portal_create(
            self,
            {
                "window_id": window.id,
                "team_id": team.id,
                "submission_note": (notes or "").strip() or False,
                "submitted_by_id": user.id,
            },
            user=user,
        )
        privilege.portal_call(
            entry,
            "action_submit",
            scope_domain=[("window_id", "=", window.id), ("team_id", "=", team.id)],
            user=user,
        )
        return entry

    def get_portal_state_label(self):
        self.ensure_one()
        return {
            "draft": _("Draft"),
            "submitted": _("Awaiting federation review"),
            "approved": _("Approved"),
            "rejected": _("Returned or rejected"),
            "withdrawn": _("Withdrawn"),
        }.get(self.state, self.state or "")
