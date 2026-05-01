import re
import unicodedata

from odoo import api, fields, models

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify_public_text(value):
    """Handle slugify public text."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_PATTERN.sub("-", ascii_value).strip("-")
    return slug or "item"


def _ics_escape(value):
    """Handle ICS escape."""
    if not value:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_format_datetime(value):
    """Handle ICS format datetime."""
    return fields.Datetime.to_datetime(value).strftime("%Y%m%dT%H%M%S")


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    _public_slug_unique = models.Constraint(
        "UNIQUE(public_slug)",
        "Public slug must be unique.",
    )

    website_published = fields.Boolean(
        string="Published on Website",
        default=False,
    )
    public_description = fields.Html(
        string="Public Description",
    )
    public_slug = fields.Char(
        string="Public Slug",
        help="Optional SEO/public URL slug override",
    )
    show_public_results = fields.Boolean(
        string="Show Public Results",
        default=True,
    )
    show_public_standings = fields.Boolean(
        string="Show Public Standings",
        default=True,
    )
    public_featured = fields.Boolean(
        string="Featured on Tournament Hub",
        default=False,
    )
    public_editorial_summary = fields.Text(
        string="Editorial Summary",
        help="Short front-page summary shown on public tournament cards and hero sections.",
    )
    public_pinned_announcement = fields.Text(
        string="Pinned Announcement",
        help="Short notice displayed prominently on the public tournament page.",
    )
    public_hero_image = fields.Binary(
        string="Public Hero Image",
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
        return self.public_slug or self.name or self.code or "tournament"

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
        return f"/tournaments/{self.get_public_slug_value()}"

    def get_public_register_path(self):
        """Return public register path."""
        self.ensure_one()
        return f"{self.get_public_path()}/register"

    def get_public_teams_path(self):
        """Return public teams path."""
        self.ensure_one()
        return f"{self.get_public_path()}/teams"

    def get_public_schedule_path(self):
        """Return public schedule path."""
        self.ensure_one()
        return f"{self.get_public_path()}/schedule"

    def get_public_results_path(self):
        """Return public results path."""
        self.ensure_one()
        return f"{self.get_public_path()}/results"

    def get_public_standings_path(self):
        """Return public standings path."""
        self.ensure_one()
        return f"{self.get_public_path()}/standings"

    def get_public_bracket_path(self):
        """Return public bracket path."""
        self.ensure_one()
        return f"{self.get_public_path()}/bracket"

    def get_public_feed_path(self):
        """Return public feed path."""
        self.ensure_one()
        return f"/api/v1/tournaments/{self.get_public_slug_value()}/feed"

    def get_public_schedule_ics_path(self):
        """Return public schedule ICS path."""
        self.ensure_one()
        return f"{self.get_public_path()}/schedule.ics"

    @api.model
    def _get_public_site_search_domain(self, search=None):
        """Return public site search domain."""
        if not search:
            return []

        search_terms = [("name", "ilike", search)]
        if "code" in self._fields:
            search_terms.append(("code", "ilike", search))
        if "location" in self._fields:
            search_terms.append(("location", "ilike", search))
        if "venue_id" in self._fields:
            search_terms.append(("venue_id.name", "ilike", search))
        if "public_editorial_summary" in self._fields:
            search_terms.append(("public_editorial_summary", "ilike", search))

        if len(search_terms) == 1:
            return [search_terms[0]]
        return ["|"] * (len(search_terms) - 1) + search_terms

    @api.model
    def get_public_published_tournaments(
        self, search=None, limit=None, extra_domain=None
    ):
        """Return public published tournaments."""
        return self.sudo().search(
            [("website_published", "=", True)]
            + self._get_public_site_search_domain(search)
            + list(extra_domain or []),
            order="date_start asc, id asc",
            limit=limit,
        )

    @api.model
    def get_public_featured_tournaments(
        self, search=None, limit=None, extra_domain=None
    ):
        """Return public featured tournaments."""
        domain = (
            [
                ("website_published", "=", True),
                ("state", "in", ("open", "in_progress")),
            ]
            + self._get_public_site_search_domain(search)
            + list(extra_domain or [])
        )
        return self.sudo().search(
            domain,
            order="public_featured desc, date_start asc, id asc",
            limit=limit,
        )

    @api.model
    def get_public_archived_tournaments(
        self, search=None, limit=None, extra_domain=None
    ):
        """Return public archived tournaments."""
        return self.sudo().search(
            [
                ("website_published", "=", True),
                ("state", "in", ("closed", "cancelled")),
            ]
            + self._get_public_site_search_domain(search)
            + list(extra_domain or []),
            order="date_start desc, id desc",
            limit=limit,
        )

    @api.model
    def get_public_live_tournaments(self, limit=None, extra_domain=None):
        """Return public live tournaments."""
        return self.sudo().search(
            [
                ("website_published", "=", True),
                ("state", "=", "in_progress"),
            ]
            + list(extra_domain or []),
            order="public_featured desc, date_start desc, id desc",
            limit=limit,
        )

    @api.model
    def get_public_recent_result_tournaments(self, limit=None, extra_domain=None):
        """Return public recent result tournaments."""
        tournaments = self.sudo().search(
            [
                ("website_published", "=", True),
                ("state", "in", ("open", "in_progress", "closed")),
            ]
            + list(extra_domain or []),
            order="write_date desc, id desc",
        )
        if not tournaments:
            return tournaments

        ranked = []
        latest_match_by_tournament = {}
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "in", tournaments.ids),
                    ("result_state", "=", "approved"),
                ],
                order="date_scheduled desc, write_date desc, id desc",
            )
        )
        for match in matches:
            latest_match_by_tournament.setdefault(match.tournament_id.id, match)
        for tournament in tournaments:
            latest_match = latest_match_by_tournament.get(tournament.id)
            if not latest_match:
                continue
            activity_dt = (
                latest_match.date_scheduled
                or latest_match.write_date
                or tournament.write_date
            )
            ranked.append((activity_dt, tournament.id))
        ranked.sort(reverse=True)
        result_ids = (
            [tournament_id for _, tournament_id in ranked[:limit]]
            if limit
            else [tournament_id for _, tournament_id in ranked]
        )
        return self.browse(result_ids)

    def can_access_public_detail(self):
        """Return whether access public detail is allowed."""
        self.ensure_one()
        return bool(self.website_published)

    def get_public_detail_context(self):
        """Return the template context dict for the tournament detail page.

        Centralises template data preparation so the controller only resolves
        the tournament and renders the response.
        """
        self.ensure_one()
        participants = (
            self.env["federation.tournament.participant"]
            .sudo()
            .search(
                [("tournament_id", "=", self.id), ("state", "!=", "withdrawn")],
                order="state asc, seed asc, team_id asc",
            )
        )
        access = self.can_access_public_detail()
        empty_matches = self.env["federation.match"].browse([])
        empty_standings = self.env["federation.standing"].browse([])
        return {
            "tournament": self,
            "participants": participants,
            "can_register": self.state == "open",
            "public_live_matches": (
                self.get_public_live_matches(limit=4) if access else empty_matches
            ),
            "upcoming_matches": (
                self.get_public_upcoming_matches(limit=4) if access else empty_matches
            ),
            "recent_results": (
                self.get_public_recent_result_matches(limit=4)
                if access
                else empty_matches
            ),
            "public_standings": (
                self.get_public_standings() if access else empty_standings
            ),
            "public_participants": (
                self.get_public_participants(limit=12) if access else participants[:12]
            ),
            "page_name": "tournament_overview",
        }

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        return super().create(
            [self._normalize_public_slug_vals(vals) for vals in vals_list]
        )

    def write(self, vals):
        """Update records with module-specific side effects."""
        vals = self._normalize_public_slug_vals(vals)
        to_publish = self.env["federation.tournament"].browse([])
        if vals.get("website_published"):
            to_publish = self.filtered(lambda record: not record.website_published)

        res = super().write(vals)

        if vals.get("website_published"):
            Dispatcher = self.env.get("federation.notification.dispatcher")
            if Dispatcher is not None:
                for record in to_publish.filtered("website_published"):
                    Dispatcher.send_tournament_published(record)

        return res

    def can_access_public_results(self):
        """Return whether access public results is allowed."""
        self.ensure_one()
        return bool(self.can_access_public_detail() and self.show_public_results)

    def can_access_public_standings(self):
        """Return whether access public standings is allowed."""
        self.ensure_one()
        return bool(self.can_access_public_detail() and self.show_public_standings)
