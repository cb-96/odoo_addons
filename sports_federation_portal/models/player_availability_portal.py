"""Portal commands for the optional player availability of clubs.

Every command resolves the team inside the caller's portal scope before it
reads or writes with elevated rights; answers through a personal link are
tied to that link's token only.
"""

from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationClubAvailabilityPortal(models.Model):
    _inherit = "federation.club"

    @api.model
    def _portal_set_player_availability(self, club_id, enabled, user=None):
        """Whole-club representatives switch player availability on or off."""
        user = user or self.env.user
        club = user.portal_club_scope_ids.filtered(lambda item: item.id == club_id)
        if not club:
            raise AccessError(_("Only representatives of the whole club can change this."))
        club.sudo().write({"player_availability_enabled": bool(enabled)})
        return club


class FederationPlayerAvailabilityPortal(models.Model):
    _inherit = "federation.player.availability.request"

    @api.model
    def _portal_teams(self, user=None):
        """Teams the user manages whose club uses player availability."""
        user = user or self.env.user
        clubs = user.portal_club_scope_ids
        teams = user.portal_team_scope_ids
        if not clubs and not teams:
            return self.env["federation.team"]
        return self.env["federation.team"].sudo().search(
            [
                "|",
                ("club_id", "in", clubs.ids),
                ("id", "in", teams.ids),
                ("club_id.player_availability_enabled", "=", True),
            ],
            order="name",
        )

    @api.model
    def _portal_enabled(self, user=None):
        return bool(self._portal_teams(user=user))

    @api.model
    def _portal_upcoming(self, user=None):
        """Upcoming published game days of the user's teams, with any request."""
        teams = self._portal_teams(user=user)
        if not teams:
            return []
        today = fields.Date.context_today(self)
        matches = self.env["federation.match"].sudo().search(
            [
                ("schedule_publication_id.state", "=", "live"),
                ("schedule_publication_id.matchday_id.date", ">=", today),
                ("state", "!=", "cancelled"),
                "|",
                ("home_team_id", "in", teams.ids),
                ("away_team_id", "in", teams.ids),
            ]
        )
        pairs = OrderedDict()
        for match in matches:
            day = match.schedule_publication_id.matchday_id
            for team in (match.home_team_id | match.away_team_id) & teams:
                pairs[(team.id, day.id)] = pairs.get((team.id, day.id), 0) + 1
        if not pairs:
            return []
        Team = self.env["federation.team"].sudo()
        Day = self.env["federation.matchday"].sudo()
        requests = {
            (request.team_id.id, request.matchday_id.id): request
            for request in self.sudo().search(
                [
                    ("team_id", "in", [key[0] for key in pairs]),
                    ("matchday_id", "in", [key[1] for key in pairs]),
                ]
            )
        }
        rows = [
            {
                "team": Team.browse(team_id),
                "matchday": Day.browse(day_id),
                "match_count": count,
                "request": requests.get((team_id, day_id)),
            }
            for (team_id, day_id), count in pairs.items()
        ]
        return sorted(
            rows, key=lambda row: (row["matchday"].date, row["team"].name or "")
        )

    @api.model
    def _portal_create(self, team_id, matchday_id, user=None):
        """Ask the team's players; returns the request and the emails queued."""
        user = user or self.env.user
        row = next(
            (
                item
                for item in self._portal_upcoming(user=user)
                if item["team"].id == team_id and item["matchday"].id == matchday_id
            ),
            None,
        )
        if not row:
            raise AccessError(_("This team does not play on that game day."))
        request = self._open_request(row["team"], row["matchday"], user=user)
        return request, request._send_invitations()

    @api.model
    def _portal_get(self, request_id, user=None):
        request = self.sudo().browse(request_id).exists()
        if not request or request.team_id not in self._portal_teams(user=user):
            raise AccessError(_("You do not have access to this availability request."))
        request._sync_players()
        return request

    def _portal_answer(self, line_id, response, user=None):
        self.ensure_one()
        line = self.line_ids.filtered(lambda item: item.id == line_id)
        if not line:
            raise ValidationError(_("Choose a player of this request."))
        line._record_response(response, by="club")
        return line

    def _portal_remind(self, user=None):
        self.ensure_one()
        if not self._is_open():
            raise ValidationError(_("This game day has already been played."))
        return self._send_invitations(only_unanswered=True, reminder=True)

    @api.model
    def _portal_lineup_availability(self, sheet):
        """Answers for the line-up page of a match sheet (rendered after access checks)."""
        sheet = sheet.sudo()
        return self._lineup_availability(
            sheet.team_id, sheet.match_id.schedule_publication_id.matchday_id
        )
