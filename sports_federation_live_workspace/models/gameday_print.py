"""Printable game-day documents: the schedule to pin at the venue and score sheets.

Both read the game day's current live publication only, so a print always
matches what teams and the public see. A match moved on the day prints on its
operational court and time.
"""

from collections import OrderedDict

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.sports_federation_calendar.time_policy import utc_to_local

CANCELLED = "cancelled"
REFEREE_CANCELLED = "cancelled"
DUTY_INACTIVE = ("draft", "rejected")


class FederationMatchdayPrint(models.Model):
    _inherit = "federation.matchday"

    def _gameday_print_matches(self):
        """Published, not cancelled matches ordered by time and court."""
        self.ensure_one()
        publication = self.current_publication_id
        Match = self.env["federation.match"]
        if not publication or publication.state != "live":
            return Match
        matches = Match.search(
            [("schedule_publication_id", "=", publication.id)]
        ).filtered(lambda match: match.state != CANCELLED and match._print_slot())
        return matches.sorted(
            lambda match: (
                match._print_slot().start_datetime,
                match._print_slot().court_id.name or "",
                match.id,
            )
        )

    def _gameday_print_assert_published(self):
        self.ensure_one()
        if not self._gameday_print_matches():
            raise UserError(
                _(
                    "%(day)s has no published matches yet. Publish its schedule "
                    "before printing.",
                    day=self.display_name,
                )
            )

    def action_print_gameday_schedule(self):
        self.ensure_one()
        self._gameday_print_assert_published()
        return self.env.ref(
            "sports_federation_live_workspace.action_report_gameday_schedule"
        ).report_action(self)

    def action_print_gameday_scoresheets(self):
        """All score sheets of the game day in schedule order, in one PDF."""
        self.ensure_one()
        self._gameday_print_assert_published()
        return self.env.ref(
            "sports_federation_rosters.action_report_match_scoresheet"
        ).report_action(self._gameday_print_matches())

    def _gameday_print_values(self):
        """Grid (time x court), per-match officials and club duties."""
        self.ensure_one()
        timezone = self.event_timezone or "UTC"
        matches = self._gameday_print_matches()
        referees = self.env["federation.match.referee"].search(
            [("match_id", "in", matches.ids), ("state", "!=", REFEREE_CANCELLED)]
        )
        duties = self.env["federation.match.club.referee.duty"].search(
            [("match_id", "in", matches.ids), ("state", "not in", DUTY_INACTIVE)]
        )
        referee_roles = dict(referees._fields["role"]._description_selection(self.env))
        duty_roles = dict(duties._fields["role"]._description_selection(self.env))

        courts = OrderedDict()
        grid = OrderedDict()
        rows = []
        for match in matches:
            slot = match._print_slot()
            start = utc_to_local(slot.start_datetime, timezone)
            end = utc_to_local(slot.end_datetime, timezone)
            time_label = start.strftime("%H:%M")
            courts.setdefault(slot.court_id.id, slot.court_id.name)
            officials = [
                "%s: %s"
                % (
                    referee_roles.get(line.role, line.role),
                    line.referee_id.display_name,
                )
                for line in referees.filtered(lambda line: line.match_id == match)
            ]
            match_duties = duties.filtered(lambda duty: duty.match_id == match)
            officials += [
                "%s: %s%s"
                % (
                    duty_roles.get(duty.role, duty.role),
                    duty.club_id.display_name,
                    (
                        " (%s)" % duty.nominated_player_id.display_name
                        if duty.nominated_player_id
                        else ""
                    ),
                )
                for duty in match_duties
            ]
            row = {
                "match": match,
                "time": time_label,
                "end": end.strftime("%H:%M"),
                "court": slot.court_id.name,
                "court_id": slot.court_id.id,
                "division": match.tournament_id.name or "",
                "home": match.home_team_id.display_name or _("To be decided"),
                "away": match.away_team_id.display_name or _("To be decided"),
                "officials": officials,
                "moved": bool(
                    match.operational_slot_id
                    and match.operational_slot_id != match.published_slot_id
                ),
            }
            rows.append(row)
            grid.setdefault(time_label, {}).setdefault(slot.court_id.id, []).append(row)

        clubs = OrderedDict()
        for duty in duties.sorted(lambda duty: (duty.club_id.name or "", duty.id)):
            row = next(item for item in rows if item["match"] == duty.match_id)
            clubs.setdefault(duty.club_id.display_name, []).append(
                {
                    "time": row["time"],
                    "court": row["court"],
                    "role": duty_roles.get(duty.role, duty.role),
                    "match": "%s – %s" % (row["home"], row["away"]),
                    "person": duty.nominated_player_id.display_name or "",
                }
            )
        return {
            "timezone": timezone,
            "date": self.date,
            "venue": self.venue_id.display_name or "",
            "courts": list(courts.items()),
            "grid": grid,
            "rows": rows,
            "club_duties": clubs,
            "publication": self.current_publication_id,
        }


class FederationMatchPrintSlot(models.Model):
    _inherit = "federation.match"

    def _print_slot(self):
        """The court and time the match is played on today."""
        self.ensure_one()
        return self.operational_slot_id or self.published_slot_id


class ReportGamedaySchedule(models.AbstractModel):
    _name = "report.sports_federation_live_workspace.report_gameday_schedule"
    _description = "Game-day schedule report"

    @api.model
    def _get_report_values(self, docids, data=None):
        days = self.env["federation.matchday"].browse(docids)
        days.check_access("read")
        return {
            "doc_ids": days.ids,
            "doc_model": "federation.matchday",
            "docs": days,
            "schedule": {day.id: day._gameday_print_values() for day in days},
        }
