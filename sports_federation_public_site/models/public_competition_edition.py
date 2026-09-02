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
