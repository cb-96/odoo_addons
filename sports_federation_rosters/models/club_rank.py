"""Club team ranking: playing up, promotion after two matches, no playing down.

When a club has several ranked teams in the same scope (same club, gender and
category, roster season and competition), team rank 1 (A) is the highest:

* a player of a lower-ranked team may be put on the roster of a higher-ranked
  team and play for it (playing up);
* after playing two matches for the higher-ranked team, the player moves to
  that team permanently. The move is stored as a promotion record, so it does
  not depend on editing roster lines that line-ups already lock;
* a player of a higher-ranked team can never play for a lower-ranked team.

A match counts once the team's line-up is approved or locked, the player is
not crossed out for that match, and the match is done.
"""

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

PROMOTION_MATCHES = 2
APPEARANCE_SHEET_STATES = ("approved", "locked")
_RANK_TOKEN = re.compile(r"^(?:([A-F])|([1-9]))$")


def _rank_from_name(name):
    """Return 1 for "... A" / "... 1", 2 for "... B" / "... 2", else 0."""
    tokens = (name or "").strip().split()
    if len(tokens) < 2:
        return 0
    match = _RANK_TOKEN.match(tokens[-1])
    if not match:
        return 0
    letter, digit = match.groups()
    return ord(letter) - ord("A") + 1 if letter else int(digit)


class FederationTeamClubRank(models.Model):
    _inherit = "federation.team"

    club_rank = fields.Integer(
        string="Rank within club",
        compute="_compute_club_rank",
        store=True,
        readonly=False,
        help="1 is the club's highest team (A), 2 the next (B), and so on. Only "
        "ranked teams of the same club, gender and category follow the "
        "playing-up rule. Filled from a name ending in A-F or 1-9; 0 means not "
        "ranked.",
    )

    @api.depends()
    def _compute_club_rank(self):
        # Computed once from the name (also for existing teams on upgrade);
        # afterwards the rank is only changed by hand.
        for team in self:
            team.club_rank = _rank_from_name(team.name)

    @api.constrains("club_rank")
    def _check_club_rank(self):
        for team in self:
            if team.club_rank < 0:
                raise ValidationError(_("The rank within the club cannot be negative."))


class FederationClubRankPromotion(models.Model):
    _name = "federation.club.rank.promotion"
    _description = "Club Team Promotion"
    _order = "date desc, id desc"

    player_id = fields.Many2one(
        "federation.player", required=True, ondelete="cascade", index=True
    )
    club_id = fields.Many2one(
        "federation.club", required=True, ondelete="cascade", index=True
    )
    season_id = fields.Many2one(
        "federation.season", required=True, ondelete="cascade", index=True
    )
    competition_id = fields.Many2one(
        "federation.competition", ondelete="set null", index=True
    )
    from_team_id = fields.Many2one(
        "federation.team", string="From team", ondelete="set null"
    )
    to_team_id = fields.Many2one(
        "federation.team", string="To team", required=True, ondelete="cascade"
    )
    to_rank = fields.Integer(string="Rank of new team", required=True)
    match_id = fields.Many2one(
        "federation.match",
        string="Deciding match",
        ondelete="set null",
        help="The second match the player played for the new team.",
    )
    date = fields.Date(required=True, default=fields.Date.context_today)
    note = fields.Text()

    _unique_player_team_season = models.Constraint(
        "UNIQUE(player_id, to_team_id, season_id)",
        "This player is already promoted to this team for this season.",
    )


class FederationClubRankService(models.AbstractModel):
    """Shared rule logic; every read runs as superuser and returns plain data."""

    _name = "federation.club.rank.service"
    _description = "Club Team Ranking Rules"

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    @api.model
    def _team_in_scope(self, team):
        return bool(team and team.club_id and team.club_rank > 0)

    @api.model
    def _scope_line_domain(self, roster):
        team = roster.team_id
        return [
            ("status", "=", "active"),
            ("roster_id.club_id", "=", team.club_id.id),
            ("roster_id.season_id", "=", roster.season_id.id),
            ("roster_id.competition_id", "=", roster.competition_id.id),
            ("roster_id.status", "!=", "closed"),
            ("roster_id.team_id.club_rank", ">", 0),
            ("roster_id.team_id.gender", "=", team.gender),
            ("roster_id.team_id.category", "=", team.category),
        ]

    @api.model
    def _scope_lines(self, roster, players=None):
        if not self._team_in_scope(roster.team_id) or not roster.season_id:
            return self.env["federation.team.roster.line"]
        domain = self._scope_line_domain(roster)
        if players is not None:
            domain.append(("player_id", "in", players.ids))
        return self.env["federation.team.roster.line"].sudo().search(domain)

    @api.model
    def _scope_promotions(self, roster, players=None):
        team = roster.team_id
        if not self._team_in_scope(team) or not roster.season_id:
            return self.env["federation.club.rank.promotion"]
        domain = [
            ("club_id", "=", team.club_id.id),
            ("season_id", "=", roster.season_id.id),
            ("competition_id", "=", roster.competition_id.id),
            ("to_team_id.gender", "=", team.gender),
            ("to_team_id.category", "=", team.category),
        ]
        if players is not None:
            domain.append(("player_id", "in", players.ids))
        return self.env["federation.club.rank.promotion"].sudo().search(domain)

    @api.model
    def _promotion_floor(self, roster, player):
        """Return the promotion with the best (lowest) rank, or an empty record."""
        promotions = self._scope_promotions(roster, player)
        return promotions.sorted("to_rank")[:1]

    # ------------------------------------------------------------------
    # Roster rule
    # ------------------------------------------------------------------

    @api.model
    def roster_block_reason(self, roster, player, exclude_lines=None):
        """Why ``player`` may not be on ``roster``; False when allowed."""
        team = roster.team_id
        if not self._team_in_scope(team) or not player:
            return False
        rank = team.club_rank
        promotion = self._promotion_floor(roster, player)
        if promotion and rank > promotion.to_rank:
            return _(
                "%(player)s moved up to %(team)s on %(date)s and can no longer "
                "play for a lower-ranked team.",
                player=player.display_name,
                team=promotion.to_team_id.display_name,
                date=promotion.date,
            )
        lines = self._scope_lines(roster, player) - (exclude_lines or self.env[
            "federation.team.roster.line"
        ])
        lines = lines.filtered(lambda line: line.roster_id.team_id != team)
        higher = lines.filtered(lambda line: line.roster_id.team_id.club_rank < rank)
        lower = lines.filtered(lambda line: line.roster_id.team_id.club_rank > rank)
        if higher and not lower:
            return _(
                "%(player)s plays for %(team)s. Players of a higher-ranked team "
                "cannot play for a lower-ranked team of the club.",
                player=player.display_name,
                team=higher.sorted(lambda line: line.roster_id.team_id.club_rank)[
                    :1
                ].roster_id.team_id.display_name,
            )
        return False

    @api.model
    def blocked_players(self, roster):
        """Players the roster's picker hides because of the ranking rule."""
        team = roster.team_id
        players = self.env["federation.player"]
        if not self._team_in_scope(team):
            return players
        rank = team.club_rank
        ranks = {}
        for line in self._scope_lines(roster):
            if line.roster_id.team_id == team:
                continue
            ranks.setdefault(line.player_id, []).append(
                line.roster_id.team_id.club_rank
            )
        for player, player_ranks in ranks.items():
            if any(r < rank for r in player_ranks) and not any(
                r > rank for r in player_ranks
            ):
                players |= player
        for promotion in self._scope_promotions(roster):
            if promotion.to_rank < rank:
                players |= promotion.player_id
        return players

    # ------------------------------------------------------------------
    # Playing up and promotion
    # ------------------------------------------------------------------

    @api.model
    def home_line(self, roster, player):
        """The lower-ranked roster line a player plays up from, if any."""
        team = roster.team_id
        if not self._team_in_scope(team):
            return self.env["federation.team.roster.line"]
        promotion = self._promotion_floor(roster, player)
        if promotion and promotion.to_rank <= team.club_rank:
            return self.env["federation.team.roster.line"]
        lower = self._scope_lines(roster, player).filtered(
            lambda line: line.roster_id.team_id.club_rank > team.club_rank
        )
        return lower.sorted(lambda line: -line.roster_id.team_id.club_rank)[:1]

    @api.model
    def appearance_count(self, roster, player, exclude_matches=None):
        """Matches ``player`` has played for the roster's team in its scope."""
        domain = [
            ("player_id", "=", player.id),
            ("crossed_out", "=", False),
            ("match_sheet_id.team_id", "=", roster.team_id.id),
            ("match_sheet_id.state", "in", APPEARANCE_SHEET_STATES),
            ("match_sheet_id.match_id.state", "=", "done"),
            ("match_sheet_id.match_id.tournament_id.season_id", "=", roster.season_id.id),
        ]
        if roster.competition_id:
            domain.append(
                (
                    "match_sheet_id.match_id.tournament_id.competition_id",
                    "=",
                    roster.competition_id.id,
                )
            )
        if exclude_matches:
            domain.append(("match_sheet_id.match_id", "not in", exclude_matches.ids))
        lines = self.env["federation.match.sheet.line"].sudo().search(domain)
        return len(lines.match_sheet_id.match_id)

    @api.model
    def promotion_warnings(self, roster, players, planned_matches):
        """Warnings for players who move up if they play ``planned_matches`` more."""
        warnings = []
        if not roster or not self._team_in_scope(roster.team_id) or planned_matches < 1:
            return warnings
        team = roster.team_id
        for player in players:
            home = self.home_line(roster, player)
            if not home:
                continue
            played = self.appearance_count(roster, player)
            needed = max(PROMOTION_MATCHES - played, 0)
            if needed > planned_matches:
                continue
            home_team = home.roster_id.team_id.display_name
            if needed <= 1:
                warnings.append(
                    _(
                        "%(player)s (%(home)s) has played %(played)s match(es) for "
                        "%(team)s. The next match for %(team)s moves %(player)s "
                        "permanently to %(team)s; %(player)s can then no longer "
                        "play for %(home)s.",
                        player=player.display_name,
                        home=home_team,
                        team=team.display_name,
                        played=played,
                    )
                )
            else:
                warnings.append(
                    _(
                        "%(player)s (%(home)s) has not played for %(team)s yet. "
                        "Playing %(needed)s matches for %(team)s today moves "
                        "%(player)s permanently to %(team)s; %(player)s can then "
                        "no longer play for %(home)s.",
                        player=player.display_name,
                        home=home_team,
                        team=team.display_name,
                        needed=needed,
                    )
                )
        return warnings

    @api.model
    def apply_promotions(self, sheets):
        """Promote players who reached the threshold through these sheets."""
        Promotion = self.env["federation.club.rank.promotion"].sudo()
        for sheet in sheets.sudo():
            if (
                sheet.state not in APPEARANCE_SHEET_STATES
                or sheet.match_id.state != "done"
                or not sheet.roster_id
                or not self._team_in_scope(sheet.team_id)
            ):
                continue
            roster = sheet.roster_id
            for line in sheet.line_ids.filtered(lambda item: not item.crossed_out):
                player = line.player_id
                home = self.home_line(roster, player)
                if not home:
                    continue
                if self.appearance_count(roster, player) < PROMOTION_MATCHES:
                    continue
                Promotion.create(
                    {
                        "player_id": player.id,
                        "club_id": sheet.team_id.club_id.id,
                        "season_id": roster.season_id.id,
                        "competition_id": roster.competition_id.id or False,
                        "from_team_id": home.roster_id.team_id.id,
                        "to_team_id": sheet.team_id.id,
                        "to_rank": sheet.team_id.club_rank,
                        "match_id": sheet.match_id.id,
                    }
                )
                self._close_lower_lines(roster, player, sheet)

    @api.model
    def _close_lower_lines(self, roster, player, sheet):
        """End the player's lower-team roster lines where line-ups allow it.

        The promotion record already blocks the player for lower teams, so a
        line that a line-up still locks only gets a note for the club.
        """
        rank = roster.team_id.club_rank
        lower = self._scope_lines(roster, player).filtered(
            lambda line: line.roster_id.team_id.club_rank > rank
        )
        message = _(
            "%(player)s played %(count)s matches for %(team)s and moved up to "
            "%(team)s permanently (deciding match: %(match)s).",
            player=player.display_name,
            count=PROMOTION_MATCHES,
            team=roster.team_id.display_name,
            match=sheet.match_id.display_name,
        )
        roster.message_post(body=message)
        for line in lower:
            try:
                with self.env.cr.savepoint():
                    line.write(
                        {"status": "removed", "date_to": fields.Date.context_today(self)}
                    )
                line.roster_id.message_post(
                    body=message + " " + _("The player was removed from this roster.")
                )
            except (UserError, ValueError) as error:
                _logger.info("Promotion kept roster line %s: %s", line.id, error)
                line.roster_id.message_post(
                    body=message
                    + " "
                    + _(
                        "The player is still listed on this roster because earlier "
                        "line-ups use the line, but can no longer play for this team."
                    )
                )


class FederationTeamRosterClubRank(models.Model):
    _inherit = "federation.team.roster"

    club_rank_blocked_player_ids = fields.Many2many(
        "federation.player",
        compute="_compute_club_rank_blocked_player_ids",
        help="Technical: players of higher-ranked teams of the club, or players "
        "who moved up, hidden from this roster's player picker.",
    )

    @api.depends("team_id.club_rank", "season_id", "competition_id")
    def _compute_club_rank_blocked_player_ids(self):
        service = self.env["federation.club.rank.service"]
        for roster in self:
            roster.club_rank_blocked_player_ids = service.blocked_players(roster)


class FederationTeamRosterLineClubRank(models.Model):
    _inherit = "federation.team.roster.line"

    club_rank_note = fields.Char(
        string="Playing up",
        compute="_compute_club_rank_note",
        help="Shown for players from a lower-ranked team of the club, with the "
        "number of matches played for this team.",
    )

    @api.depends("player_id", "roster_id.team_id.club_rank", "status")
    def _compute_club_rank_note(self):
        service = self.env["federation.club.rank.service"]
        for line in self:
            note = False
            if line.player_id and line.roster_id and line.status == "active":
                home = service.home_line(line.roster_id, line.player_id)
                if home:
                    note = _(
                        "From %(team)s · %(played)s/%(limit)s matches",
                        team=home.roster_id.team_id.display_name,
                        played=service.appearance_count(line.roster_id, line.player_id),
                        limit=PROMOTION_MATCHES,
                    )
            line.club_rank_note = note

    @api.constrains("player_id", "roster_id", "status")
    def _check_club_rank_rule(self):
        service = self.env["federation.club.rank.service"]
        for line in self.filtered(lambda item: item.status == "active"):
            reason = service.roster_block_reason(
                line.roster_id, line.player_id, exclude_lines=line
            )
            if reason:
                raise ValidationError(reason)


class FederationMatchSheetClubRank(models.Model):
    _inherit = "federation.match.sheet"

    club_rank_warning = fields.Text(
        string="Team promotion warning",
        compute="_compute_club_rank_warning",
    )

    @api.depends(
        "team_id",
        "roster_id",
        "line_ids.player_id",
        "line_ids.crossed_out",
        "match_id.state",
    )
    def _compute_club_rank_warning(self):
        service = self.env["federation.club.rank.service"]
        for sheet in self:
            planned = 0 if sheet.match_id.state in ("done", "cancelled") else 1
            players = sheet.line_ids.filtered(lambda line: not line.crossed_out).player_id
            warnings = service.promotion_warnings(sheet.roster_id, players, planned)
            sheet.club_rank_warning = "\n".join(warnings) or False

    def write(self, vals):
        result = super().write(vals)
        if "state" in vals:
            self.env["federation.club.rank.service"].apply_promotions(self)
        return result


class FederationMatchSheetLineClubRank(models.Model):
    _inherit = "federation.match.sheet.line"

    def write(self, vals):
        result = super().write(vals)
        if "crossed_out" in vals:
            self.env["federation.club.rank.service"].apply_promotions(
                self.match_sheet_id
            )
        return result

    def _get_eligibility_reasons(self):
        reasons = super()._get_eligibility_reasons()
        sheet = self.match_sheet_id
        if self.player_id and sheet.roster_id:
            service = self.env["federation.club.rank.service"]
            promotion = service._promotion_floor(sheet.roster_id, self.player_id)
            if promotion and sheet.team_id.club_rank > promotion.to_rank:
                reasons.append(
                    _(
                        "%(player)s moved up to %(team)s and can no longer play "
                        "for a lower-ranked team.",
                        player=self.player_id.display_name,
                        team=promotion.to_team_id.display_name,
                    )
                )
        return list(dict.fromkeys(reasons))


class FederationMatchClubRank(models.Model):
    _inherit = "federation.match"

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "done":
            sheets = self.env["federation.match.sheet"].sudo().search(
                [("match_id", "in", self.ids)]
            )
            self.env["federation.club.rank.service"].apply_promotions(sheets)
        return result


class FederationPlayerClubRank(models.Model):
    _inherit = "federation.player"

    club_rank_promotion_ids = fields.One2many(
        "federation.club.rank.promotion",
        "player_id",
        string="Team promotions",
    )
