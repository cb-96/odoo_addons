"""Confirm a permanent competition deletion after seeing exactly what goes."""

from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

CONFIRMATION_WORD = "DELETE"


class FederationCompetitionForceDeleteWizard(models.TransientModel):
    _name = "federation.competition.force.delete.wizard"
    _description = "Delete Competitions Permanently"

    edition_ids = fields.Many2many(
        "federation.competition.edition",
        "federation_force_delete_wizard_edition_rel",
        "wizard_id",
        "edition_id",
        string="Competitions",
        context={"active_test": False},
        readonly=True,
    )
    include_parent = fields.Boolean(
        string="Also delete the parent competition when nothing else uses it",
    )
    preview_html = fields.Html(compute="_compute_preview", sanitize=True)
    blocked = fields.Boolean(compute="_compute_preview")
    confirmation = fields.Char(
        string="Type DELETE to confirm",
        help="Deletion cannot be undone.",
    )

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        context = self.env.context
        if context.get("active_model") == "federation.competition.edition":
            ids = context.get("active_ids") or [context.get("active_id")]
            values["edition_ids"] = [fields.Command.set([i for i in ids if i])]
        return values

    @api.depends("edition_ids", "include_parent")
    def _compute_preview(self):
        service = self.env["federation.competition.force.delete"]
        for wizard in self:
            if not wizard.edition_ids:
                wizard.preview_html = False
                wizard.blocked = True
                continue
            scope = service.collect(
                wizard.edition_ids, include_parent=wizard.include_parent
            )
            parts = []
            published = wizard.edition_ids.filtered(
                lambda edition: "website_published" in edition._fields
                and edition.website_published
            )
            if published:
                parts.append(
                    "<div class='alert alert-danger' role='alert'>%s</div>"
                    % escape(
                        _(
                            "Unpublish from the website first: %(names)s",
                            names=", ".join(published.mapped("display_name")),
                        )
                    )
                )
            if scope["blockers"]:
                parts.append(
                    "<div class='alert alert-danger' role='alert'><p>%s</p><ul>%s</ul></div>"
                    % (
                        escape(
                            _(
                                "Nothing can be deleted because other data depends on it:"
                            )
                        ),
                        "".join(
                            "<li>%s</li>" % escape(item) for item in scope["blockers"]
                        ),
                    )
                )
            warnings = service.warnings(scope)
            if warnings:
                parts.append(
                    "<div class='alert alert-warning' role='alert'><p>%s</p><ul>%s</ul></div>"
                    % (
                        escape(
                            _(
                                "This also removes history that is normally kept as evidence:"
                            )
                        ),
                        "".join("<li>%s</li>" % escape(item) for item in warnings),
                    )
                )
            rows = "".join(
                "<tr><td>%s</td><td class='text-end'>%s</td></tr>"
                % (escape(label), count)
                for label, count in service.summary(scope)
            )
            parts.append(
                "<table class='table table-sm'><thead><tr><th>%s</th><th class='text-end'>%s</th>"
                "</tr></thead><tbody>%s</tbody></table>"
                % (escape(_("Will be deleted")), escape(_("Records")), rows)
            )
            parts.append(
                "<p class='text-muted small'>%s</p>"
                % escape(
                    _(
                        "Clubs, teams, players, licences, seasons, registrations, rosters, "
                        "venues and referees are kept."
                    )
                )
            )
            wizard.preview_html = "".join(parts)
            wizard.blocked = bool(scope["blockers"] or published)

    def _competitions_action(self):
        for xmlid in (
            "sports_federation_setup_flow.action_competition_setup_home",
            "sports_federation_tournament.federation_competition_edition_action",
        ):
            if self.env.ref(xmlid, raise_if_not_found=False):
                return self.env["ir.actions.actions"]._for_xml_id(xmlid)
        return {"type": "ir.actions.act_window_close"}

    def action_delete(self):
        self.ensure_one()
        if (self.confirmation or "").strip() != CONFIRMATION_WORD:
            raise UserError(_("Type DELETE to confirm the permanent deletion."))
        names = ", ".join(self.edition_ids.mapped("display_name"))
        self.env["federation.competition.force.delete"].execute(
            self.edition_ids, include_parent=self.include_parent
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Deleted permanently"),
                "message": _(
                    "%(names)s and everything in it were deleted.", names=names
                ),
                "type": "success",
                "next": self._competitions_action(),
            },
        }
