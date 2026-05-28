import re
import unicodedata

from odoo import api, fields, models

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value):
    """Return a URL-safe slug for *value*."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_PATTERN.sub("-", ascii_value).strip("-")
    return slug or "club"


class FederationClub(models.Model):
    _inherit = "federation.club"

    _public_slug_unique = models.Constraint(
        "UNIQUE(public_slug)",
        "Public club slug must be unique.",
    )

    website_published = fields.Boolean(
        string="Published on Website",
        default=False,
        tracking=True,
    )
    public_slug = fields.Char(
        string="Public Slug",
        help="Readable URL slug for the public club page.",
    )

    # ------------------------------------------------------------------
    # Slug helpers (same pattern as tournament / team)
    # ------------------------------------------------------------------

    def _normalize_public_slug_vals(self, vals):
        """Return vals with a normalised public_slug value."""
        normalized = dict(vals)
        if "public_slug" in normalized:
            normalized["public_slug"] = (
                _slugify(normalized["public_slug"])
                if normalized.get("public_slug")
                else False
            )
        return normalized

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(
            [self._normalize_public_slug_vals(v) for v in vals_list]
        )

    def write(self, vals):
        return super().write(self._normalize_public_slug_vals(vals))

    def _get_public_slug_seed(self):
        """Return the seed string used to derive the computed slug."""
        self.ensure_one()
        return self.public_slug or self.name or self.code or "club"

    def get_public_slug_value(self):
        """Return the effective public slug (explicit or auto-computed)."""
        self.ensure_one()
        if self.public_slug:
            return self.public_slug
        return f"{_slugify(self._get_public_slug_seed())}-{self.id}"

    @api.model
    def resolve_public_slug(self, slug_value, extra_domain=None):
        """Look up a club by slug; return an empty recordset when not found."""
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
        """Return the canonical public URL for this club."""
        self.ensure_one()
        return f"/clubs/{self.get_public_slug_value()}"

    # ------------------------------------------------------------------
    # Recent tournament participation helper
    # ------------------------------------------------------------------

    def get_recent_participations(self, seasons=3):
        """Return participants for the club's teams from the last *seasons* seasons."""
        self.ensure_one()
        team_ids = self.team_ids.ids
        if not team_ids:
            return self.env["federation.tournament.participant"].browse([])
        Season = self.env["federation.season"].sudo()
        recent_seasons = Season.search([], order="date_end desc, id desc", limit=seasons)
        if not recent_seasons:
            return self.env["federation.tournament.participant"].browse([])
        return (
            self.env["federation.tournament.participant"]
            .sudo()
            .search(
                [
                    ("team_id", "in", team_ids),
                    ("tournament_id.website_published", "=", True),
                    ("tournament_id.season_id", "in", recent_seasons.ids),
                    ("state", "!=", "withdrawn"),
                ],
                order="tournament_id desc, id asc",
            )
        )
