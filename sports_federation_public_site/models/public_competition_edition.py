import re

from odoo import api, fields, models


class FederationCompetitionEditionPublic(models.Model):
    _inherit = "federation.competition.edition"

    website_published = fields.Boolean(index=True, tracking=True)
    public_slug = fields.Char(index=True, copy=False)
    public_featured = fields.Boolean(index=True)
    public_summary = fields.Text()
    public_hero_image = fields.Binary(attachment=True)
    public_sort_sequence = fields.Integer(default=10)
    public_archive_date = fields.Date()

    _public_slug_unique = models.Constraint(
        "unique(public_slug)", "The public competition slug must be unique."
    )

    @api.onchange("name")
    def _onchange_public_slug(self):
        for record in self:
            if record.name and not record.public_slug:
                record.public_slug = re.sub(
                    r"[^a-z0-9]+", "-", record.name.lower()
                ).strip("-")

    def action_publish_website(self):
        for edition in self:
            self.env["federation.public.competition.queries"].assert_publishable(
                edition
            )
            edition.write({"website_published": True})
        return True

    def action_unpublish_website(self):
        self.write({"website_published": False})
        return True

    def action_open_public_preview(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/competitions/{self.public_slug or 'preview'}?preview=1",
            "target": "new",
        }

    def get_public_api_path(self):
        self.ensure_one()
        return f"/api/v1/competitions/{self.public_slug}"

    def get_public_api_payload(self):
        self.ensure_one()
        divisions = self.env["federation.public.competition.queries"].public_divisions(
            self
        )
        return {
            "api_version": "v1",
            "contract": "competition_feed",
            "competition": {
                "id": self.id,
                "name": self.name,
                "slug": self.public_slug,
                "state": self.state,
                "season": (
                    {"id": self.season_id.id, "name": self.season_id.display_name}
                    if self.season_id
                    else None
                ),
                "date_start": (
                    fields.Date.to_string(self.date_start) if self.date_start else None
                ),
                "date_end": (
                    fields.Date.to_string(self.date_end) if self.date_end else None
                ),
                "summary": self.public_summary or None,
                "website_url": f"/competitions/{self.public_slug}",
                "api_url": self.get_public_api_path(),
            },
            "divisions": [division.get_public_feed_payload() for division in divisions],
            "privacy": {
                "scope": "published competition data only",
                "excluded": [
                    "contact details",
                    "personal data",
                    "internal notes",
                    "disciplinary data",
                    "unpublished schedules",
                    "draft or unapproved results",
                ],
            },
        }
