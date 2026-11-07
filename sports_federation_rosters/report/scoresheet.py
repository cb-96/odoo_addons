"""Printable match scoresheet.

The sheet is the paper fallback for a match: it is printed before the game day
with everything the federation already knows (teams, officials, approved
line-ups) and completed by hand at the court. Values are prepared here so the
template stays free of business logic and works for a blank sheet too.
"""

import re
from urllib.parse import quote

from odoo import api, fields, models

# The sheet lists the team's game-day line-up (up to 14 players). Per match at
# most 12 may play (WDBF 4.1): the others are crossed out at the court, because
# the per-match selection is made minutes before the start, after printing.
# WDBF cloth rules 2026 further: two halves (9.1) with one time-out per team
# per half (9.8.1), two challenges per team (37.1), two blue cards (33.3).
PLAYER_ROWS = 14
DEFAULT_MATCH_PLAYERS = 12
SETS_PER_HALF = 15
HALVES = ("1st half", "2nd half")
ASSISTANT_SLOTS = 5
CHALLENGE_BOXES = 2
ASSISTANT_ROLE_ORDER = ("assistant_1", "assistant_2", "fourth", "table")
# Points per set when the competition does not configure them (10.2-10.3).
DEFAULT_SET_POINTS = (2, 1)


def _jersey_sort_key(line):
    """Numeric shirt numbers first, in numeric order, then the rest."""
    number = (line.jersey_number or "").strip()
    if re.fullmatch(r"\d+", number):
        return (0, int(number), "")
    return (1, 0, number or line.player_id.name or "")


class ReportFederationScoresheet(models.AbstractModel):
    _name = "report.sports_federation_rosters.report_match_scoresheet"
    _description = "Match Scoresheet Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        matches = self.env["federation.match"].browse(docids).exists()
        return {
            "doc_ids": matches.ids,
            "doc_model": "federation.match",
            "docs": matches,
            "sheets": [self._scoresheet_values(match) for match in matches],
            "challenge_boxes": range(CHALLENGE_BOXES),
            "company": self.env.company,
            "printed_on": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ).strftime("%d/%m/%Y %H:%M"),
        }

    @api.model
    def _scoresheet_values(self, match):
        kickoff = (
            fields.Datetime.context_timestamp(self, match.date_scheduled)
            if match.date_scheduled
            else False
        )
        tournament = match.tournament_id
        competition = (
            tournament.edition_id.display_name
            if "edition_id" in tournament._fields and tournament.edition_id
            else (
                tournament.competition_id.display_name
                if "competition_id" in tournament._fields
                and tournament.competition_id
                else ""
            )
        )
        head, assistants = self._officials(match)
        win_points, draw_points = self._set_points(match)
        teams = [
            self._team_values(match, "home", match.home_team_id, "A"),
            self._team_values(match, "away", match.away_team_id, "B"),
        ]
        return {
            "match": match,
            "reference": match.name or "",
            "competition": competition,
            "division": tournament.display_name or "",
            "date": kickoff.strftime("%d/%m/%Y") if kickoff else "",
            "time": kickoff.strftime("%H:%M") if kickoff else "",
            "venue": self._venue(match),
            "head_referee": head,
            "assistants": assistants,
            "teams": teams,
            "lineups_final": all(team["lineup_final"] for team in teams),
            "qr_src": self._qr_src(match),
            "halves": [
                {
                    "label": label,
                    "sets": list(range(first, first + SETS_PER_HALF)),
                }
                for label, first in zip(
                    HALVES, range(1, len(HALVES) * SETS_PER_HALF, SETS_PER_HALF)
                )
            ],
            "win_points": win_points,
            "draw_points": draw_points,
            "result_known": match.state == "done",
        }

    @api.model
    def _set_points(self, match):
        """Points per won and drawn set, from the competition when configured."""
        edition = match._competition_workflow_edition()
        if (
            edition
            and "court_set_win_points" in edition._fields
            and edition.court_scoring_mode == "sets"
        ):
            return edition.court_set_win_points, edition.court_set_draw_points
        return DEFAULT_SET_POINTS

    @api.model
    def _qr_src(self, match):
        """QR code that opens the match in the backend, for result entry."""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        target = f"{base_url}/odoo/federation.match/{match.id}"
        return (
            "/report/barcode/?barcode_type=QR&value=%s&width=180&height=180"
            % quote(target, safe="")
        )

    @api.model
    def _venue(self, match):
        parts = []
        if "venue_id" in match._fields and match.venue_id:
            parts.append(match.venue_id.name)
        if "playing_area_id" in match._fields and match.playing_area_id:
            parts.append(match.playing_area_id.name)
        return " – ".join(parts)

    @api.model
    def _officials(self, match):
        assistants = [""] * ASSISTANT_SLOTS
        if "referee_assignment_ids" not in match._fields:
            return "", assistants
        assignments = match.referee_assignment_ids.filtered(
            lambda item: item.state != "cancelled"
        )
        head = assignments.filtered(lambda item: item.role == "head")[:1]
        others = assignments.filtered(lambda item: item.role != "head").sorted(
            lambda item: (
                (
                    ASSISTANT_ROLE_ORDER.index(item.role)
                    if item.role in ASSISTANT_ROLE_ORDER
                    else len(ASSISTANT_ROLE_ORDER)
                ),
                item.id,
            )
        )
        for index, assignment in enumerate(others[:ASSISTANT_SLOTS]):
            assistants[index] = assignment.referee_id.name or ""
        return head.referee_id.name or "", assistants

    @api.model
    def _team_values(self, match, side, team, letter):
        sheet = match.match_sheet_ids.filtered(
            lambda item: item.side == side and item.team_id == team
        )[:1]
        # Print the whole game-day line-up. Players already crossed out for
        # this match when printing are shown struck through; the rest are
        # crossed out by hand at the court.
        lines = sorted(sheet.line_ids, key=_jersey_sort_key)
        captain = next((line for line in lines if line.is_captain), None)
        players = [
            {
                "number": line.jersey_number or "",
                "name": line.player_id.name or "",
                "captain": line.is_captain,
                "crossed_out": line.crossed_out,
            }
            for line in lines
        ]
        players += [
            {"number": "", "name": "", "captain": False, "crossed_out": False}
            for _index in range(max(PLAYER_ROWS - len(players), 0))
        ]
        return {
            "letter": letter,
            "name": team.display_name or "",
            "coach": sheet.coach_name or "",
            "assistant_coach": sheet.manager_name or "",
            "captain": captain.player_id.name if captain else "",
            "players": players,
            # Printed line-ups that are not approved yet must be checked
            # against the player passes before play.
            "lineup_final": sheet.state in ("approved", "locked"),
            "match_players": sheet.match_participant_limit or DEFAULT_MATCH_PLAYERS,
        }
