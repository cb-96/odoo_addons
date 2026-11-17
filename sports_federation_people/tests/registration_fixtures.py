"""Annual club season registration for test fixtures.

A player plays for a club only with an active licence (club season
registration) for the competition season. Tests that are about rosters, match
sheets or portals, not about registration itself, use this helper to give
their fixture players that registration.

The licence covers the whole season and today, so roster and match-sheet
reference dates inside or around the season are covered. Players without a
club are attached to ``club``; players of another club are left alone, so a
test can still prove that a foreign player is refused.
"""

from datetime import timedelta

from odoo import fields


def register_for_season(players, season, club=None):
    """Give ``players`` an active licence for ``season``; return the licences."""
    env = players.env(su=True)
    License = env["federation.player.license"]
    today = fields.Date.context_today(License)
    starts = [day for day in (season.date_start, today) if day]
    ends = [day for day in (season.date_end, today) if day]
    issue_date = min(starts) - timedelta(days=1)
    expiry_date = max(ends) + timedelta(days=366)
    licences = License.browse()
    for player in players.sudo():
        if not player.club_id and club:
            player.write({"club_id": club.id})
        if not player.club_id or (club and player.club_id != club):
            continue
        licence = License.search(
            [("player_id", "=", player.id), ("season_id", "=", season.id)], limit=1
        )
        if not licence:
            licence = License.create(
                {
                    "player_id": player.id,
                    "club_id": player.club_id.id,
                    "season_id": season.id,
                    "issue_date": issue_date,
                    "expiry_date": expiry_date,
                    "state": "active",
                }
            )
        elif licence.club_id == player.club_id and licence.state != "active":
            licence.write(
                {
                    "issue_date": min(licence.issue_date, issue_date),
                    "expiry_date": max(licence.expiry_date, expiry_date),
                    "state": "active",
                }
            )
        licences |= licence
    return licences


def register_club_players(club, season):
    """Register every active player of ``club`` for ``season``."""
    players = club.env(su=True)["federation.player"].search([("club_id", "=", club.id)])
    return register_for_season(players, season, club)


def create_registered_roster_lines(Line, vals_list):
    """Create roster lines after registering their players for the roster season.

    Use it as ``create_registered_roster_lines(env["federation.team.roster.line"],
    vals)`` wherever a test needs eligible players on a roster.
    """
    single = isinstance(vals_list, dict)
    env = Line.env
    for vals in [vals_list] if single else vals_list:
        roster = env["federation.team.roster"].browse(vals["roster_id"])
        player = env["federation.player"].browse(vals["player_id"])
        if roster.season_id:
            register_for_season(player, roster.season_id, roster.team_id.club_id)
    return Line.create(vals_list)
