"""Optional player availability per game day.

A club decides whether it uses this (many clubs already ask their players in
Spond or a group chat). When it is on, a team manager asks the roster players
of a team whether they can play on a game day. Players answer through a
personal link in their email, without an account; the club can also enter an
answer itself. The answers are shown next to the players when the game-day
line-up is made. Nothing is selected automatically.
"""

import secrets

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

RESPONSES = [
    ("pending", "No answer yet"),
    ("yes", "Available"),
    ("maybe", "Maybe"),
    ("no", "Not available"),
]
BADGES = {
    "pending": "text-bg-light border",
    "yes": "text-bg-success",
    "maybe": "text-bg-warning",
    "no": "text-bg-danger",
}


def _new_token():
    return secrets.token_urlsafe(24)


class FederationClubAvailabilitySetting(models.Model):
    _inherit = "federation.club"

    player_availability_enabled = fields.Boolean(
        string="Ask players for their availability",
        default=False,
        tracking=True,
        help="When on, team managers can ask roster players before each game day "
        "whether they can play, and see the answers when making the line-up. "
        "Leave it off if the club already uses another app for this.",
    )


class FederationPlayerAvailabilityRequest(models.Model):
    _name = "federation.player.availability.request"
    _description = "Player availability request"
    _order = "matchday_date desc, id desc"

    team_id = fields.Many2one(
        "federation.team", required=True, ondelete="cascade", index=True
    )
    club_id = fields.Many2one(related="team_id.club_id", store=True, index=True)
    matchday_id = fields.Many2one(
        "federation.matchday", string="Game day", required=True, ondelete="cascade"
    )
    matchday_date = fields.Date(related="matchday_id.date", store=True)
    requested_by_id = fields.Many2one("res.users", readonly=True)
    line_ids = fields.One2many("federation.player.availability", "request_id")
    yes_count = fields.Integer(compute="_compute_counts")
    maybe_count = fields.Integer(compute="_compute_counts")
    no_count = fields.Integer(compute="_compute_counts")
    pending_count = fields.Integer(compute="_compute_counts")

    _unique_team_matchday = models.Constraint(
        "UNIQUE(team_id, matchday_id)",
        "A team asks its players once per game day.",
    )

    @api.depends("line_ids.response")
    def _compute_counts(self):
        for request in self:
            responses = request.line_ids.mapped("response")
            request.yes_count = responses.count("yes")
            request.maybe_count = responses.count("maybe")
            request.no_count = responses.count("no")
            request.pending_count = responses.count("pending")

    def _is_open(self):
        """Answers can change until the game day has passed."""
        self.ensure_one()
        return bool(
            self.matchday_date
            and self.matchday_date >= fields.Date.context_today(self)
        )

    # ------------------------------------------------------------------
    # Players
    # ------------------------------------------------------------------

    @api.model
    def _team_players(self, team, matchday):
        """Active roster players of the team that the game day falls in."""
        day = matchday.date
        lines = self.env["federation.team.roster.line"].sudo().search(
            [
                ("roster_id.team_id", "=", team.id),
                ("roster_id.status", "!=", "closed"),
                ("status", "=", "active"),
            ]
        )
        lines = lines.filtered(
            lambda line: (
                not day
                or (
                    (not line.roster_id.season_id.date_start
                     or line.roster_id.season_id.date_start <= day)
                    and (not line.roster_id.season_id.date_end
                         or line.roster_id.season_id.date_end >= day)
                )
            )
        )
        return lines.mapped("player_id").sorted(
            lambda player: (player.last_name or "", player.first_name or "")
        )

    def _sync_players(self):
        """Add roster players who joined after the request was made."""
        Line = self.env["federation.player.availability"].sudo()
        for request in self:
            known = request.line_ids.mapped("player_id")
            missing = self._team_players(request.team_id, request.matchday_id) - known
            if missing:
                Line.create(
                    [{"request_id": request.id, "player_id": p.id} for p in missing]
                )

    @api.model
    def _open_request(self, team, matchday, user=None):
        """Return the team's request for the game day, creating it if needed."""
        user = user or self.env.user
        if not team.club_id.player_availability_enabled:
            raise UserError(
                _("%(club)s does not use player availability.", club=team.club_id.name)
            )
        if not matchday.date or matchday.date < fields.Date.context_today(self):
            raise ValidationError(_("This game day has already been played."))
        request = self.sudo().search(
            [("team_id", "=", team.id), ("matchday_id", "=", matchday.id)], limit=1
        )
        if not request:
            request = self.sudo().create(
                {
                    "team_id": team.id,
                    "matchday_id": matchday.id,
                    "requested_by_id": user.id,
                }
            )
        request._sync_players()
        return request

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def _send_invitations(self, only_unanswered=False, reminder=False):
        """Queue one email per player with an email address. Returns the count."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.player_id.email)
        if only_unanswered:
            lines = lines.filtered(lambda line: line.response == "pending")
        else:
            lines = lines.filtered(lambda line: not line.invited_on)
        Mail = self.env["mail.mail"].sudo()
        now = fields.Datetime.now()
        for line in lines:
            Mail.create(line._invitation_mail_values(reminder=reminder))
            line.sudo().write(
                {"reminded_on": now} if reminder else {"invited_on": now}
            )
        return len(lines)

    def _availability_by_player(self):
        """{player_id: line} for this request."""
        self.ensure_one()
        return {line.player_id.id: line for line in self.line_ids}

    @api.model
    def _lineup_availability(self, team, matchday):
        """Answers to show next to players in a line-up; empty when not used."""
        if not team or not matchday or not team.club_id.player_availability_enabled:
            return {}
        request = self.sudo().search(
            [("team_id", "=", team.id), ("matchday_id", "=", matchday.id)], limit=1
        )
        if not request:
            return {}
        return {
            player_id: {
                "response": line.response,
                "label": line.response_label,
                "badge": BADGES[line.response],
                "note": line.note or "",
            }
            for player_id, line in request._availability_by_player().items()
        }


class FederationPlayerAvailability(models.Model):
    _name = "federation.player.availability"
    _description = "Player availability answer"
    _order = "player_id"

    request_id = fields.Many2one(
        "federation.player.availability.request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    player_id = fields.Many2one("federation.player", required=True, ondelete="cascade")
    response = fields.Selection(RESPONSES, default="pending", required=True)
    response_label = fields.Char(compute="_compute_response_label")
    note = fields.Char(help="Optional, for example 'only the first match'.")
    responded_on = fields.Datetime(readonly=True)
    answered_by = fields.Selection(
        [("player", "Player"), ("club", "Club")], readonly=True
    )
    access_token = fields.Char(
        required=True, copy=False, index=True, default=lambda self: _new_token()
    )
    invited_on = fields.Datetime(readonly=True)
    reminded_on = fields.Datetime(readonly=True)

    _unique_request_player = models.Constraint(
        "UNIQUE(request_id, player_id)",
        "A player answers once per game day.",
    )
    _unique_token = models.Constraint(
        "UNIQUE(access_token)", "Availability links must be unique."
    )

    @api.depends("response")
    @api.depends_context("lang")
    def _compute_response_label(self):
        labels = dict(self._fields["response"]._description_selection(self.env))
        for line in self:
            line.response_label = labels.get(line.response, line.response)

    def _record_response(self, response, note=None, by="player"):
        self.ensure_one()
        if response not in dict(RESPONSES) or response == "pending":
            raise ValidationError(_("Choose Available, Maybe or Not available."))
        if not self.request_id._is_open():
            raise ValidationError(_("This game day has already been played."))
        self.sudo().write(
            {
                "response": response,
                "note": (note or "").strip()[:200] or False,
                "responded_on": fields.Datetime.now(),
                "answered_by": by,
            }
        )

    @api.model
    def _from_token(self, token):
        """The answer behind a personal link, or an empty recordset."""
        if not token or len(token) < 20:
            return self.browse()
        return self.sudo().search([("access_token", "=", token)], limit=1)

    def _public_url(self):
        self.ensure_one()
        base = self.get_base_url()
        return "%s/availability/%s" % (base, self.access_token)

    def _invitation_mail_values(self, reminder=False):
        self.ensure_one()
        request = self.request_id
        day = request.matchday_id
        when = fields.Date.to_string(day.date) if day.date else ""
        subject = (
            _("Reminder: can you play on %(date)s?", date=when)
            if reminder
            else _("Can you play on %(date)s?", date=when)
        )
        intro = _(
            "%(team)s plays on %(date)s at %(venue)s. Let your team know whether "
            "you can play.",
            team=request.team_id.display_name,
            date=when,
            venue=day.venue_id.display_name or "",
        )
        body = Markup(
            "<p>%s</p><p>%s</p><p><a href=\"%s\">%s</a></p><p><small>%s</small></p>"
        ) % (
            escape(_("Hello %s,", self.player_id.first_name or self.player_id.name)),
            escape(intro),
            self._public_url(),
            escape(_("Give your answer")),
            escape(
                _("You can change your answer with the same link until the game day.")
            ),
        )
        company = self.env.company
        return {
            "subject": subject,
            "body_html": body,
            "email_to": self.player_id.email,
            "email_from": company.email_formatted or company.partner_id.email_formatted,
            "auto_delete": True,
        }
