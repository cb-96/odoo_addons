from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .public_tournament_flags import (
    _ics_escape,
    _ics_format_datetime,
    _slugify_public_text,
)


class FederationSeason(models.Model):
    _inherit = "federation.season"

    _public_slug_unique = models.Constraint(
        "UNIQUE(public_slug)",
        "Public season slug must be unique.",
    )

    website_published = fields.Boolean(
        string="Published on Website",
        default=False,
    )
    public_slug = fields.Char(
        string="Public Slug",
        help="Optional readable slug seed for public season pages.",
    )
    public_summary = fields.Text(
        string="Public Summary",
        help="Short summary shown in season discovery sections and season landing pages.",
    )
    public_description = fields.Html(
        string="Public Description",
    )

    def _normalize_public_slug_vals(self, vals):
        """Normalize public slug vals."""
        normalized = dict(vals)
        if "public_slug" in normalized:
            normalized["public_slug"] = (
                _slugify_public_text(normalized["public_slug"])
                if normalized.get("public_slug")
                else False
            )
        return normalized

    def _get_public_slug_seed(self):
        """Return public slug seed."""
        self.ensure_one()
        return self.public_slug or self.name or self.code or "season"

    def get_public_slug_value(self):
        """Return public slug value."""
        self.ensure_one()
        if self.public_slug:
            return self.public_slug
        return f"{_slugify_public_text(self._get_public_slug_seed())}-{self.id}"

    @api.model
    def resolve_public_slug(self, slug_value, extra_domain=None):
        """Resolve public slug."""
        if not slug_value:
            return self.browse([])

        extra_domain = list(extra_domain or [])

        explicit = self.sudo().search(
            [("public_slug", "=", slug_value)] + extra_domain,
            limit=1,
        )
        if explicit:
            return explicit

        tail = slug_value.rsplit("-", 1)[-1]
        if not tail.isdigit():
            return self.browse([])

        record = self.sudo().search(
            [("id", "=", int(tail))] + extra_domain,
            limit=1,
        )
        if record and record.get_public_slug_value() == slug_value:
            return record
        return self.browse([])

    def get_public_path(self):
        """Return public path."""
        self.ensure_one()
        return f"/seasons/{self.get_public_slug_value()}"

    def can_access_public_detail(self):
        """Return whether access public detail is allowed."""
        self.ensure_one()
        return bool(self.website_published)

    @api.model
    def get_public_published_seasons(self, limit=None):
        """Return public published seasons."""
        seasons = self.sudo().search(
            [("website_published", "=", True)],
            order="date_start desc, id desc",
        )
        return seasons[:limit] if limit else seasons

    def get_public_tournaments(self, limit=None):
        """Return public tournaments."""
        self.ensure_one()
        Tournament = self.env["federation.tournament"]
        tournaments = Tournament.get_public_featured_tournaments(
            extra_domain=[("season_id", "=", self.id)]
        )
        return tournaments[:limit] if limit else tournaments

    def get_public_recent_tournaments(self, limit=None):
        """Return public recent tournaments."""
        self.ensure_one()
        Tournament = self.env["federation.tournament"]
        tournaments = Tournament.get_public_recent_result_tournaments(
            extra_domain=[("season_id", "=", self.id)]
        )
        return tournaments[:limit] if limit else tournaments

    def get_public_editorial_items(self, limit=None):
        """Return public editorial items."""
        self.ensure_one()
        Editorial = self.env["federation.public.editorial.item"]
        return Editorial.get_live_items(season=self, limit=limit)

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        return super().create(
            [self._normalize_public_slug_vals(vals) for vals in vals_list]
        )

    def write(self, vals):
        """Update records with module-specific side effects."""
        return super().write(self._normalize_public_slug_vals(vals))


class FederationPublicEditorialItem(models.Model):
    _name = "federation.public.editorial.item"
    _description = "Federation Public Editorial Item"
    _order = "publish_start desc, sequence asc, id desc"

    PUBLICATION_STATE_SELECTION = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]
    CONTENT_TYPE_SELECTION = [
        ("highlight", "Highlight"),
        ("announcement", "Announcement"),
        ("update", "Update"),
    ]

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    publication_state = fields.Selection(
        PUBLICATION_STATE_SELECTION,
        required=True,
        default="draft",
    )
    content_type = fields.Selection(
        CONTENT_TYPE_SELECTION,
        required=True,
        default="highlight",
    )
    kicker = fields.Char()
    summary = fields.Text(required=True)
    body_html = fields.Html()
    publish_start = fields.Datetime()
    publish_end = fields.Datetime()
    season_id = fields.Many2one("federation.season", ondelete="cascade")
    tournament_id = fields.Many2one("federation.tournament", ondelete="cascade")
    team_id = fields.Many2one("federation.team", ondelete="cascade")

    @api.constrains("publish_start", "publish_end")
    def _check_publish_window(self):
        """Validate publish window."""
        for record in self:
            if (
                record.publish_start
                and record.publish_end
                and record.publish_end < record.publish_start
            ):
                raise ValidationError(
                    "Publish end cannot be earlier than publish start."
                )

    @api.constrains("season_id", "tournament_id", "team_id")
    def _check_public_target_anchor(self):
        """Validate public target anchor."""
        for record in self:
            if not (record.season_id or record.tournament_id or record.team_id):
                raise ValidationError(
                    "Editorial items must be linked to a season, tournament, or team."
                )

    def action_schedule(self):
        """Schedule the editorial item for publication."""
        for record in self:
            if record.publication_state != "draft":
                raise ValidationError("Only draft items can be scheduled.")
            if not record.publish_start:
                raise ValidationError("Set a publish start date before scheduling.")
            record.publication_state = "scheduled"

    def action_publish(self):
        """Publish the editorial item immediately."""
        for record in self:
            if record.publication_state not in ("draft", "scheduled"):
                raise ValidationError("Only draft or scheduled items can be published.")
            record.publication_state = "published"

    def action_archive_item(self):
        """Archive a published or scheduled editorial item."""
        for record in self:
            if record.publication_state not in ("published", "scheduled"):
                raise ValidationError(
                    "Only published or scheduled items can be archived."
                )
            record.publication_state = "archived"

    def action_reset_to_draft(self):
        """Reset an archived or scheduled item back to draft."""
        for record in self:
            if record.publication_state not in ("archived", "scheduled"):
                raise ValidationError(
                    "Only archived or scheduled items can be reset to draft."
                )
            record.publication_state = "draft"

    def can_access_publicly(self, reference_dt=None):
        """Return whether access publicly is allowed."""
        self.ensure_one()
        if not self.active or self.publication_state in ("draft", "archived"):
            return False

        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        if self.publish_start and self.publish_start > reference_dt:
            return False
        if self.publish_end and self.publish_end < reference_dt:
            return False
        return True

    def get_public_target_url(self):
        """Return public target URL."""
        self.ensure_one()
        if self.team_id and self.team_id.can_access_public_profile():
            return self.team_id.get_public_path()
        if self.tournament_id and self.tournament_id.can_access_public_detail():
            return self.tournament_id.get_public_path()
        if self.season_id and self.season_id.can_access_public_detail():
            return self.season_id.get_public_path()
        return False

    @api.model
    def get_live_items(self, season=None, tournament=None, team=None, limit=None):
        """Return live items."""
        domain = [
            ("active", "=", True),
            ("publication_state", "in", ("scheduled", "published")),
        ]
        if season:
            domain.append(("season_id", "=", season.id))
        if tournament:
            domain.append(("tournament_id", "=", tournament.id))
        if team:
            domain.append(("team_id", "=", team.id))

        items = self.sudo().search(
            domain, order="publish_start desc, sequence asc, id desc"
        )
        now = fields.Datetime.now()
        items = items.filtered(lambda item: item.can_access_publicly(reference_dt=now))
        return items[:limit] if limit else items


class FederationTeamPublicFollow(models.Model):
    _inherit = "federation.team"

    def get_public_schedule_path(self):
        """Return public schedule path."""
        self.ensure_one()
        return f"{self.get_public_path()}/schedule"

    def get_public_results_path(self):
        """Return public results path."""
        self.ensure_one()
        return f"{self.get_public_path()}/results"

    def get_public_schedule_ics_path(self):
        """Return public schedule ICS path."""
        self.ensure_one()
        return f"{self.get_public_path()}/schedule.ics"

    def get_public_feed_path(self):
        """Return public feed path."""
        self.ensure_one()
        return f"/api/v1/teams/{self.get_public_slug_value()}/feed"

    def get_public_schedule_sections(self):
        """Return public schedule sections."""
        self.ensure_one()
        Match = self.env["federation.match"].sudo().browse([])
        sections = []
        section_index = {}

        for match in self.get_public_upcoming_matches():
            tournament = match.tournament_id
            if tournament:
                key = f"tournament-{tournament.id}"
                title = tournament.name
                subtitle = tournament.season_id.name if tournament.season_id else False
            else:
                key = "matches"
                title = "Upcoming Matches"
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

    def get_public_result_sections(self):
        """Return public result sections."""
        self.ensure_one()
        Match = self.env["federation.match"].sudo().browse([])
        sections = []
        section_index = {}

        for match in self.get_public_recent_result_matches():
            tournament = match.tournament_id
            if tournament:
                key = f"tournament-{tournament.id}"
                title = tournament.name
                subtitle = tournament.season_id.name if tournament.season_id else False
            else:
                key = "results"
                title = "Recent Results"
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

    def get_public_schedule_ics(self):
        """Return public schedule ICS."""
        self.ensure_one()
        events = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Sports Federation//Team Schedule//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{_ics_escape(self.name)}",
        ]
        for match in self.get_public_upcoming_matches().filtered("date_scheduled"):
            start_dt = fields.Datetime.to_datetime(match.date_scheduled)
            end_dt = start_dt + timedelta(hours=1)
            opponent = (
                match.away_team_id if match.home_team_id == self else match.home_team_id
            )
            summary = f"{self.name} vs {opponent.name if opponent else 'TBD'}"
            description_parts = (
                [match.tournament_id.name] if match.tournament_id else [self.name]
            )
            if match.round_id:
                description_parts.append(match.round_id.name)
            if match.stage_id:
                description_parts.append(match.stage_id.name)

            events.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:team-{self.id}-match-{match.id}@sportsfederation",
                    f"DTSTAMP:{_ics_format_datetime(fields.Datetime.now())}",
                    f"DTSTART:{_ics_format_datetime(start_dt)}",
                    f"DTEND:{_ics_format_datetime(end_dt)}",
                    f"SUMMARY:{_ics_escape(summary)}",
                    f"DESCRIPTION:{_ics_escape(' | '.join(description_parts))}",
                    f"URL:{_ics_escape(self.get_public_schedule_path())}",
                    "END:VEVENT",
                ]
            )
        events.append("END:VCALENDAR")
        return "\r\n".join(events) + "\r\n"

    def get_public_feed_payload(self):
        """Return public feed payload."""
        self.ensure_one()
        return {
            "api_version": "v1",
            "team": {
                "id": self.id,
                "name": self.name,
                "slug": self.get_public_slug_value(),
                "club": self.club_id.name if self.club_id else None,
                "category": self.category or None,
                "gender": self.gender or None,
                "public_url": self.get_public_path(),
                "schedule_url": self.get_public_schedule_path(),
                "results_url": self.get_public_results_path(),
                "schedule_ics_url": self.get_public_schedule_ics_path(),
                "feed_url": self.get_public_feed_path(),
            },
            "tournaments": [
                {
                    "id": tournament.id,
                    "name": tournament.name,
                    "public_url": tournament.get_public_path(),
                }
                for tournament in self.get_public_tournaments(limit=12)
            ],
            "schedule_sections": [
                {
                    "title": section["title"],
                    "subtitle": section["subtitle"],
                    "matches": [
                        match.tournament_id._serialize_public_match(match)
                        for match in section["matches"]
                    ],
                }
                for section in self.get_public_schedule_sections()
            ],
            "result_sections": [
                {
                    "title": section["title"],
                    "subtitle": section["subtitle"],
                    "matches": [
                        match.tournament_id._serialize_public_match(match)
                        for match in section["matches"]
                    ],
                }
                for section in self.get_public_result_sections()
            ],
            "standing_lines": [
                {
                    "standing": line.standing_id.public_title or line.standing_id.name,
                    "rank": line.rank,
                    "points": line.points,
                    "tournament": (
                        line.standing_id.tournament_id.name
                        if line.standing_id.tournament_id
                        else None
                    ),
                    "tournament_url": (
                        line.standing_id.tournament_id.get_public_path()
                        if line.standing_id.tournament_id
                        else None
                    ),
                }
                for line in self.get_public_standing_lines(limit=12)
            ],
        }
