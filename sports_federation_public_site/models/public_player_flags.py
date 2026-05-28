import re
import unicodedata

from odoo import api, fields, models

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value):
    """Return a URL-safe slug for *value*."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_PATTERN.sub("-", ascii_value).strip("-")
    return slug or "player"


class FederationPlayer(models.Model):
    _inherit = "federation.player"

    _public_slug_unique = models.Constraint(
        "UNIQUE(public_slug)",
        "Public player slug must be unique.",
    )

    public_visible = fields.Boolean(
        string="Visible on Public Site",
        default=False,
        tracking=True,
        help="When enabled, this player appears on the public /players listing.",
    )
    public_slug = fields.Char(
        string="Public Slug",
        help="Readable URL slug for the public player profile page.",
    )

    # ------------------------------------------------------------------
    # Slug helpers
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
        return super().create([self._normalize_public_slug_vals(v) for v in vals_list])

    def write(self, vals):
        return super().write(self._normalize_public_slug_vals(vals))

    def _get_public_slug_seed(self):
        self.ensure_one()
        return (
            self.public_slug
            or self.name
            or f"{self.first_name or ''}-{self.last_name or ''}"
            or "player"
        )

    def get_public_slug_value(self):
        """Return the effective public slug (explicit or auto-computed)."""
        self.ensure_one()
        if self.public_slug:
            return self.public_slug
        return f"{_slugify(self._get_public_slug_seed())}-{self.id}"

    @api.model
    def resolve_public_slug(self, slug_value, extra_domain=None):
        """Look up a player by slug; return an empty recordset when not found."""
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
        """Return the canonical public URL for this player."""
        self.ensure_one()
        return f"/players/{self.get_public_slug_value()}"

    # ------------------------------------------------------------------
    # Season-by-season appearance count helper
    # ------------------------------------------------------------------

    def get_public_season_appearances(self):
        """Return a list of dicts {season, count} for public display."""
        self.ensure_one()
        Roster = self.env.get("federation.roster.entry")
        if Roster is None:
            return []
        entries = Roster.sudo().search(
            [("player_id", "=", self.id)],
            order="id asc",
        )
        seasons = {}
        for entry in entries:
            season = entry.season_id if hasattr(entry, "season_id") else None
            if season is None:
                # Try to get via match → tournament → season
                continue
            sid = season.id
            seasons.setdefault(sid, {"season": season, "count": 0})
            seasons[sid]["count"] += 1
        return list(seasons.values())
