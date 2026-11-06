"""Game-day declaration sharing; lifecycle and eligibility remain on match sheets."""
from datetime import datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationMatchSheetGameday(models.Model):
    _inherit = "federation.match.sheet"

    def _get_gameday_scope(self):
        """Return the explicit match-day scope, or a tournament/date fallback."""
        self.ensure_one()
        match = self.match_id
        publication = (
            match.schedule_publication_id
            if "schedule_publication_id" in match._fields
            else False
        )
        matchday = (
            publication.matchday_id
            if publication and "matchday_id" in publication._fields
            else False
        )
        if matchday:
            return ("matchday", matchday.id)
        scheduled_date = (
            match.round_id.round_date
            if match.round_id and match.round_id.round_date
            else (
                fields.Datetime.to_datetime(match.date_scheduled).date()
                if match.date_scheduled
                else False
            )
        )
        if scheduled_date and match.tournament_id:
            return (
                "tournament_date",
                match.tournament_id.id,
                scheduled_date,
            )
        return False

    def _get_gameday_sheets(self):
        """Return all sheets sharing this team's game-day declaration scope."""
        self.ensure_one()
        scope = self._get_gameday_scope()
        if not scope:
            return self
        domain = [
            ("team_id", "=", self.team_id.id),
            ("match_id.state", "!=", "cancelled"),
        ]
        if scope[0] == "matchday":
            domain.append(
                ("match_id.schedule_publication_id.matchday_id", "=", scope[1])
            )
        else:
            day_start = datetime.combine(scope[2], time.min)
            day_end = day_start + timedelta(days=1)
            matches = self.env["federation.match"].search(
                [
                    ("tournament_id", "=", scope[1]),
                    ("state", "!=", "cancelled"),
                    "|",
                    ("round_id.round_date", "=", scope[2]),
                    "&",
                    ("date_scheduled", ">=", fields.Datetime.to_string(day_start)),
                    ("date_scheduled", "<", fields.Datetime.to_string(day_end)),
                ]
            )
            domain.append(("match_id", "in", matches.ids))
        return self.search(domain, order="match_kickoff asc, id asc")

    def _declared_lineup_signature(self):
        """Return the match-independent portion of a game-day lineup."""
        self.ensure_one()
        lines = sorted(
            (
                line.player_id.id,
                line.roster_line_id.id or False,
                bool(line.is_starter),
                bool(line.is_substitute),
                bool(line.is_captain),
                line.jersey_number or "",
            )
            for line in self.line_ids
        )
        return (self.roster_id.id or False, tuple(lines))

    def _get_existing_gameday_lineup_source(self):
        """Choose an existing declaration to initialize a newly-created sheet."""
        self.ensure_one()
        candidates = (self._get_gameday_sheets() - self).filtered("line_ids")
        if not candidates:
            return self.env["federation.match.sheet"]
        state_rank = {"locked": 4, "approved": 3, "submitted": 2, "draft": 1}
        return candidates.sorted(
            key=lambda sheet: (-state_rank.get(sheet.state, 0), sheet.id)
        )[:1]

    def _copy_declared_lineup_from(self, source, inherit_approval=False):
        """Copy only declaration fields; substitutions remain match-specific."""
        self.ensure_one()
        source.ensure_one()
        if self == source:
            return False
        if self.state in ("approved", "locked"):
            if self._declared_lineup_signature() != source._declared_lineup_signature():
                raise ValidationError(
                    _(
                        "Game-day match sheets for team '%(team)s' must use the "
                        "same approved lineup."
                    )
                    % {"team": self.team_id.display_name}
                )
            return False

        target_vals = {"roster_id": source.roster_id.id or False}
        if source.coach_name and not self.coach_name:
            target_vals["coach_name"] = source.coach_name
        if source.manager_name and not self.manager_name:
            target_vals["manager_name"] = source.manager_name
        self.write(target_vals)
        crossed_out_players = set(
            self.line_ids.filtered("crossed_out").mapped("player_id").ids
        )
        self.line_ids.unlink()
        line_values = [
            {
                "match_sheet_id": self.id,
                "player_id": line.player_id.id,
                "roster_line_id": line.roster_line_id.id or False,
                "is_starter": line.is_starter,
                "is_substitute": line.is_substitute,
                "is_captain": line.is_captain,
                "jersey_number": line.jersey_number,
                "crossed_out": line.player_id.id in crossed_out_players,
            }
            for line in source.line_ids
        ]
        if line_values:
            self.env["federation.match.sheet.line"].create(line_values)
        if inherit_approval and source.state in ("approved", "locked"):
            self.write({"state": "approved"})
            self._log_audit_event(
                "match_sheet_approved",
                _(
                    "Match sheet '%(sheet)s' inherited the approved game-day lineup."
                )
                % {"sheet": self.display_name},
            )
        elif inherit_approval and source.state == "submitted":
            self.write({"state": "submitted"})
        return True

    def _inherit_existing_gameday_lineup(self):
        """Initialize new sheets from a previously declared lineup for the day."""
        for record in self.filtered(lambda sheet: sheet.state == "draft"):
            source = record._get_existing_gameday_lineup_source()
            if source:
                record._copy_declared_lineup_from(source, inherit_approval=True)

    def _synchronize_gameday_lineup(self, source):
        """Apply one declaration to every mutable sheet in the game-day scope."""
        source.ensure_one()
        sheets = source._get_gameday_sheets()
        for sheet in sheets - source:
            sheet._copy_declared_lineup_from(source)
        return sheets

    def _get_action_gameday_groups(self):
        """Yield one selected source and complete sheet set per game-day scope."""
        seen = set()
        for record in self:
            scope = (
                record.team_id.id,
                record._get_gameday_scope() or ("sheet", record.id),
            )
            if scope in seen:
                continue
            seen.add(scope)
            yield record, record._get_gameday_sheets()
