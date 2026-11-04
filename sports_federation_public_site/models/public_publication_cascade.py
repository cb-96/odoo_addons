"""Publish a competition on the website in one click.

Publishing used to require, in order: a public slug, opening the competition,
opening and publishing each division separately, and a division could only be
started with legacy stages that the competition workspace never creates.

``Publish website`` on the competition now prepares all of that itself:

* a public slug is derived from the name when missing;
* a draft competition is opened (divisions with a frozen format follow);
* every division whose teams and format are set is published with it.

Divisions that are not ready stay unpublished and are reported.  The existing
publishability checks still run before the competition goes live.
"""
import re

from odoo import _, models
from odoo.exceptions import ValidationError


class FederationCompetitionEditionPublishCascade(models.Model):
    _inherit = "federation.competition.edition"

    def _website_ready_divisions(self):
        self.ensure_one()
        return self.tournament_ids.filtered(
            lambda division: division.active
            and division.state != "cancelled"
            and (
                getattr(division, "has_workspace_format", False)
                or division.stage_ids
            )
        )

    def _unique_public_slug(self):
        self.ensure_one()
        base = re.sub(r"[^a-z0-9]+", "-", (self.name or "competition").lower()).strip("-")
        base = base or "competition"
        slug = base
        suffix = 2
        while self.with_context(active_test=False).search_count(
            [("public_slug", "=", slug), ("id", "!=", self.id)]
        ):
            slug = "%s-%s" % (base, suffix)
            suffix += 1
        return slug

    def _prepare_website_publication(self):
        self.ensure_one()
        if "is_practice" in self._fields and self.is_practice:
            raise ValidationError(
                _("Practice competitions cannot be published on the public website.")
            )
        ready = self._website_ready_divisions()
        if not ready:
            raise ValidationError(
                _(
                    "Set the teams and format of at least one division in the "
                    "competition workspace before publishing the competition."
                )
            )
        if not self.public_slug:
            self.public_slug = self._unique_public_slug()
        if self.state == "draft":
            self.transition_competition_state(
                "open", reason=_("Opened to publish the competition on the website.")
            )
        if hasattr(ready, "_follow_competition_state"):
            # Competitions opened before this upgrade: bring their workspace
            # divisions to the competition state.
            ready._follow_competition_state(self.state)
        ready.filtered(lambda division: division.state == "draft").filtered(
            lambda division: not getattr(division, "has_workspace_format", False)
        ).action_open()
        ready.filtered(lambda division: not division.website_published).write(
            {"website_published": True}
        )
        return self.tournament_ids.filtered("active") - ready

    def action_publish_website(self):
        not_ready = self.env["federation.tournament"]
        for edition in self:
            not_ready |= edition._prepare_website_publication()
        super().action_publish_website()
        message = _("The competition and its divisions are now on the website.")
        if not_ready:
            message += " " + _(
                "Not published yet (teams or format missing): %(divisions)s.",
                divisions=", ".join(not_ready.mapped("display_name")),
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Published on the website"),
                "message": message,
                "type": "warning" if not_ready else "success",
                "sticky": bool(not_ready),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_unpublish_website(self):
        result = super().action_unpublish_website()
        self.mapped("tournament_ids").filtered("website_published").write(
            {"website_published": False}
        )
        return result
