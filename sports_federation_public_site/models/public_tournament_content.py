from datetime import timedelta

from odoo import fields, models

from .public_tournament_flags import _ics_escape, _ics_format_datetime


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    def get_public_standings(self):
        """Return public standings."""
        self.ensure_one()
        return (
            self.env["federation.standing"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("website_published", "=", True),
                ],
                order="stage_id asc, group_id asc, id asc",
            )
        )

    def get_public_participants(self, limit=None):
        """Return public participants."""
        self.ensure_one()
        participants = (
            self.env["federation.tournament.participant"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("state", "!=", "withdrawn"),
                ],
                order="state asc, team_id asc, id asc",
            )
        )
        return participants[:limit] if limit else participants

    def get_public_result_matches(self):
        """Return public result matches."""
        self.ensure_one()
        return (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("result_state", "=", "approved"),
                ],
                order="scheduled_date asc, date_scheduled asc, id asc",
            )
        )

    def get_public_recent_result_matches(self, limit=None):
        """Return public recent result matches."""
        self.ensure_one()
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("result_state", "=", "approved"),
                ],
                order="date_scheduled desc, scheduled_date desc, id desc",
            )
        )
        return matches[:limit] if limit else matches

    def get_public_schedule_matches(self):
        """Return public schedule matches."""
        self.ensure_one()
        return (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("state", "in", ("draft", "scheduled", "in_progress")),
                ],
                order="scheduled_date asc, date_scheduled asc, round_number asc, id asc",
            )
        )

    def get_public_live_matches(self, limit=None):
        """Return public live matches."""
        self.ensure_one()
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("state", "=", "in_progress"),
                ],
                order="date_scheduled asc, id asc",
            )
        )
        return matches[:limit] if limit else matches

    def get_public_upcoming_matches(self, limit=None):
        """Return public upcoming matches."""
        self.ensure_one()
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    ("state", "in", ("draft", "scheduled", "in_progress")),
                ],
                order="date_scheduled asc, scheduled_date asc, id asc",
            )
        )
        matches = matches.filtered(
            lambda record: record.date_scheduled or record.scheduled_date
        )
        return matches[:limit] if limit else matches

    def get_public_schedule_sections(self):
        """Return public schedule sections."""
        self.ensure_one()
        Match = self.env["federation.match"].sudo().browse([])
        sections = []
        section_index = {}

        for match in self.get_public_schedule_matches():
            if match.round_id:
                key = f"round-{match.round_id.id}"
                title = match.round_id.name
                subtitle = (
                    fields.Date.to_string(match.round_id.round_date)
                    if match.round_id.round_date
                    else False
                )
            elif match.stage_id:
                key = f"stage-{match.stage_id.id}"
                title = match.stage_id.name
                subtitle = (
                    fields.Date.to_string(match.scheduled_date)
                    if match.scheduled_date
                    else False
                )
            elif match.scheduled_date:
                key = f"date-{match.scheduled_date}"
                title = fields.Date.to_string(match.scheduled_date)
                subtitle = False
            else:
                key = "unscheduled"
                title = "Unscheduled"
                subtitle = False

            if key not in section_index:
                section_index[key] = len(sections)
                sections.append(
                    {
                        "key": key,
                        "title": title,
                        "subtitle": subtitle,
                        "matches": Match,
                    }
                )
            sections[section_index[key]]["matches"] |= match

        return sections

    def has_public_bracket(self):
        """Return whether the record has public bracket."""
        self.ensure_one()
        return bool(self.get_public_bracket_sections())

    def get_public_bracket_sections(self):
        """Return public bracket sections."""
        self.ensure_one()
        Match = self.env["federation.match"].sudo().browse([])
        bracket_matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", self.id),
                    "|",
                    ("bracket_type", "!=", False),
                    "|",
                    ("source_match_1_id", "!=", False),
                    ("source_match_2_id", "!=", False),
                ],
                order="round_number asc, date_scheduled asc, id asc",
            )
        )
        sections = []
        section_index = {}
        bracket_labels = dict(
            self.env["federation.match"]._fields["bracket_type"].selection
        )

        for match in bracket_matches:
            round_label = (
                f"Round {match.round_number}" if match.round_number else "Bracket"
            )
            bracket_label = bracket_labels.get(match.bracket_type, "Main")
            title = f"{bracket_label} {round_label}"
            key = f"{match.bracket_type or 'main'}-{match.round_number or 0}"

            if key not in section_index:
                section_index[key] = len(sections)
                sections.append(
                    {
                        "key": key,
                        "title": title,
                        "matches": Match,
                    }
                )
            sections[section_index[key]]["matches"] |= match

        return sections

    def _serialize_public_match(self, match):
        """Serialize public match."""
        return {
            "id": match.id,
            "name": match.name,
            "state": match.state,
            "result_state": (
                match.result_state if "result_state" in match._fields else False
            ),
            "stage": match.stage_id.name if match.stage_id else None,
            "round": match.round_id.name if match.round_id else None,
            "round_number": match.round_number or None,
            "bracket_type": match.bracket_type or None,
            "scheduled_date": (
                fields.Date.to_string(match.scheduled_date)
                if match.scheduled_date
                else None
            ),
            "kickoff": (
                fields.Datetime.to_string(match.date_scheduled)
                if match.date_scheduled
                else None
            ),
            "home_team": match.home_team_id.name if match.home_team_id else None,
            "home_team_url": (
                match.home_team_id.get_public_path() if match.home_team_id else None
            ),
            "away_team": match.away_team_id.name if match.away_team_id else None,
            "away_team_url": (
                match.away_team_id.get_public_path() if match.away_team_id else None
            ),
            "home_score": match.home_score,
            "away_score": match.away_score,
            "venue": (
                match.venue_id.name
                if "venue_id" in match._fields and match.venue_id
                else None
            ),
            "playing_area": (
                match.playing_area_id.name
                if "playing_area_id" in match._fields and match.playing_area_id
                else None
            ),
            "source_match_1": (
                match.source_match_1_id.name if match.source_match_1_id else None
            ),
            "source_match_2": (
                match.source_match_2_id.name if match.source_match_2_id else None
            ),
        }

    def get_public_schedule_ics(self):
        """Return public schedule ICS."""
        self.ensure_one()
        events = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Sports Federation//Tournament Schedule//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{_ics_escape(self.name)}",
        ]
        for match in self.get_public_schedule_matches().filtered("date_scheduled"):
            start_dt = fields.Datetime.to_datetime(match.date_scheduled)
            end_dt = start_dt + timedelta(hours=1)
            summary = f"{match.home_team_id.name if match.home_team_id else 'TBD'} vs {match.away_team_id.name if match.away_team_id else 'TBD'}"
            location_parts = []
            if "venue_id" in match._fields and match.venue_id:
                location_parts.append(match.venue_id.name)
            if "playing_area_id" in match._fields and match.playing_area_id:
                location_parts.append(match.playing_area_id.name)

            description_parts = [self.name]
            if match.round_id:
                description_parts.append(match.round_id.name)
            if match.stage_id:
                description_parts.append(match.stage_id.name)

            events.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:tournament-{self.id}-match-{match.id}@sportsfederation",
                    f"DTSTAMP:{_ics_format_datetime(fields.Datetime.now())}",
                    f"DTSTART:{_ics_format_datetime(start_dt)}",
                    f"DTEND:{_ics_format_datetime(end_dt)}",
                    f"SUMMARY:{_ics_escape(summary)}",
                    f"DESCRIPTION:{_ics_escape(' | '.join(description_parts))}",
                    f"LOCATION:{_ics_escape(', '.join(location_parts))}",
                    f"URL:{_ics_escape(self.get_public_schedule_path())}",
                    "END:VEVENT",
                ]
            )
        events.append("END:VCALENDAR")
        return "\r\n".join(events) + "\r\n"

    def get_public_feed_payload(self):
        """Return public feed payload."""
        self.ensure_one()
        participants = self.get_public_participants()
        standings = self.get_public_standings()

        return {
            "api_version": "v1",
            "tournament": {
                "id": self.id,
                "name": self.name,
                "slug": self.get_public_slug_value(),
                "code": self.code,
                "state": self.state,
                "date_start": (
                    fields.Date.to_string(self.date_start) if self.date_start else None
                ),
                "date_end": (
                    fields.Date.to_string(self.date_end) if self.date_end else None
                ),
                "public_slug": self.public_slug or None,
                "public_url": self.get_public_path(),
                "register_url": self.get_public_register_path(),
                "teams_url": self.get_public_teams_path(),
                "schedule_url": self.get_public_schedule_path(),
                "results_url": self.get_public_results_path(),
                "standings_url": self.get_public_standings_path(),
                "bracket_url": self.get_public_bracket_path(),
                "feed_url": self.get_public_feed_path(),
                "schedule_ics_url": self.get_public_schedule_ics_path(),
                "show_public_results": self.show_public_results,
                "show_public_standings": self.show_public_standings,
                "featured": self.public_featured,
                "editorial_summary": self.public_editorial_summary or None,
                "pinned_announcement": self.public_pinned_announcement or None,
            },
            "participants": [
                {
                    "id": participant.id,
                    "team": participant.team_id.name if participant.team_id else None,
                    "team_url": (
                        participant.team_id.get_public_path()
                        if participant.team_id
                        else None
                    ),
                    "club": participant.club_id.name if participant.club_id else None,
                    "state": participant.state,
                }
                for participant in participants
            ],
            "schedule_sections": [
                {
                    "title": section["title"],
                    "subtitle": section["subtitle"],
                    "matches": [
                        self._serialize_public_match(match)
                        for match in section["matches"]
                    ],
                }
                for section in self.get_public_schedule_sections()
            ],
            "bracket_sections": [
                {
                    "title": section["title"],
                    "matches": [
                        self._serialize_public_match(match)
                        for match in section["matches"]
                    ],
                }
                for section in self.get_public_bracket_sections()
            ],
            "results": [
                self._serialize_public_match(match)
                for match in self.get_public_result_matches()
            ],
            "standings": [
                {
                    "id": standing.id,
                    "name": standing.public_title or standing.name,
                    "stage": standing.stage_id.name if standing.stage_id else None,
                    "group": standing.group_id.name if standing.group_id else None,
                    "lines": [
                        {
                            "rank": line.rank,
                            "team": line.team_id.name if line.team_id else None,
                            "team_url": (
                                line.team_id.get_public_path() if line.team_id else None
                            ),
                            "played": line.played,
                            "won": line.won,
                            "drawn": line.drawn,
                            "lost": line.lost,
                            "score_for": line.score_for,
                            "score_against": line.score_against,
                            "score_diff": line.score_diff,
                            "points": line.points,
                        }
                        for line in standing.line_ids.sorted(lambda record: record.rank)
                    ],
                }
                for standing in standings
            ],
        }
