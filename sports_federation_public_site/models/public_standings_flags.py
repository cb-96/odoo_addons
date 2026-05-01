from odoo import api, fields, models

from .public_tournament_flags import _slugify_public_text


class FederationStanding(models.Model):
    _inherit = "federation.standing"

    website_published = fields.Boolean(
        string="Published on Website",
        default=False,
    )
    public_title = fields.Char(
        string="Public Title",
    )


class FederationTeam(models.Model):
    _inherit = "federation.team"

    _public_slug_unique = models.Constraint(
        "UNIQUE(public_slug)",
        "Public team slug must be unique.",
    )

    public_participant_ids = fields.One2many(
        "federation.tournament.participant",
        "team_id",
        string="Public Tournament Participants",
    )
    public_home_match_ids = fields.One2many(
        "federation.match",
        "home_team_id",
        string="Public Home Matches",
    )
    public_away_match_ids = fields.One2many(
        "federation.match",
        "away_team_id",
        string="Public Away Matches",
    )

    public_slug = fields.Char(
        string="Public Slug",
        help="Optional readable slug seed for public team pages.",
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
        if self.public_slug:
            return self.public_slug
        club_name = self.club_id.name if self.club_id else False
        return "-".join(filter(None, [self.name, club_name])) or self.code or "team"

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
        return f"/teams/{self.get_public_slug_value()}"

    def can_access_public_profile(self):
        """Return whether access public profile is allowed."""
        self.ensure_one()
        Participant = self.env["federation.tournament.participant"].sudo()
        if Participant.search_count(
            [
                ("team_id", "=", self.id),
                ("state", "!=", "withdrawn"),
                ("tournament_id.website_published", "=", True),
            ],
            limit=1,
        ):
            return True

        Match = self.env["federation.match"].sudo()
        return bool(
            Match.search_count(
                [
                    ("tournament_id.website_published", "=", True),
                    "|",
                    ("home_team_id", "=", self.id),
                    ("away_team_id", "=", self.id),
                ],
                limit=1,
            )
        )

    def get_public_tournaments(self, limit=None):
        """Return public tournaments."""
        self.ensure_one()
        tournaments = (
            self.env["federation.tournament"]
            .sudo()
            .search(
                [
                    ("website_published", "=", True),
                    ("participant_ids.team_id", "=", self.id),
                ],
                order="date_start desc, id desc",
            )
        )
        return tournaments[:limit] if limit else tournaments

    def get_public_recent_result_matches(self, limit=None):
        """Return public recent result matches."""
        self.ensure_one()
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id.website_published", "=", True),
                    ("result_state", "=", "approved"),
                    "|",
                    ("home_team_id", "=", self.id),
                    ("away_team_id", "=", self.id),
                ],
                order="date_scheduled desc, scheduled_date desc, id desc",
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
                    ("tournament_id.website_published", "=", True),
                    ("state", "in", ("draft", "scheduled", "in_progress")),
                    "|",
                    ("home_team_id", "=", self.id),
                    ("away_team_id", "=", self.id),
                ],
                order="date_scheduled asc, scheduled_date asc, id asc",
            )
        )
        matches = matches.filtered(
            lambda record: record.date_scheduled or record.scheduled_date
        )
        return matches[:limit] if limit else matches

    def get_public_standing_lines(self, limit=None):
        """Return public standing lines."""
        self.ensure_one()
        lines = (
            self.env["federation.standing.line"]
            .sudo()
            .search(
                [
                    ("team_id", "=", self.id),
                    ("standing_id.website_published", "=", True),
                ],
                order="id desc",
            )
        )
        return lines[:limit] if limit else lines

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        return super().create(
            [self._normalize_public_slug_vals(vals) for vals in vals_list]
        )

    def write(self, vals):
        """Update records with module-specific side effects."""
        return super().write(self._normalize_public_slug_vals(vals))
