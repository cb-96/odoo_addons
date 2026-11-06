"""Practice competitions: realistic sample data that never reaches the public.

A practice competition is an ordinary competition built through the same
commands as a real one, so everything an operator sees in it is what a real
competition looks like.  It is only marked ``is_practice`` so that it

* cannot be published on the public website or in the public API,
* shows a clear "Practice" marker in lists and forms, and
* can be removed (archived) in one click together with its sample clubs.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

PRACTICE_PREFIX = "[Practice]"
PRACTICE_CODE_PREFIX = "PRACTICE-"


class FederationCompetitionEditionPractice(models.Model):
    _inherit = "federation.competition.edition"

    is_practice = fields.Boolean(
        string="Practice competition",
        copy=False,
        index=True,
        readonly=True,
        help="Sample competition for trying out the workflow. "
        "It can never be published on the public website.",
    )
    practice_created_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    practice_club_ids = fields.Many2many(
        "federation.club",
        "federation_practice_edition_club_rel",
        "edition_id",
        "club_id",
        readonly=True,
        copy=False,
    )

    def write(self, values):
        if values.get("website_published") and any(self.mapped("is_practice")):
            raise ValidationError(
                _("Practice competitions cannot be published on the public website.")
            )
        return super().write(values)

    def action_open_practice_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Practice Competition"),
            "res_model": "federation.practice.competition.wizard",
            "view_mode": "form",
            "target": "new",
        }

    def action_remove_practice_competition(self):
        """Archive the practice competition, its divisions and unused sample data.

        Archiving (instead of deleting) keeps immutable publications and audit
        records intact while removing everything from the operator's lists.
        """
        practice = self.filtered("is_practice")
        if practice != self:
            raise ValidationError(
                _("Only practice competitions can be removed this way.")
            )
        for edition in practice:
            edition.activity_ids.unlink()
            for record in edition._practice_activity_targets():
                record.activity_ids.filtered(
                    lambda activity: activity.user_id == edition.practice_created_by_id
                ).unlink()
            divisions = edition.with_context(active_test=False).tournament_ids
            divisions.write({"active": False})
            clubs = edition.practice_club_ids
            still_used = self.search(
                [
                    ("id", "not in", practice.ids),
                    ("is_practice", "=", True),
                    ("practice_club_ids", "in", clubs.ids),
                ]
            ).mapped("practice_club_ids")
            unused = clubs - still_used
            if unused:
                self.env["federation.team"].search(
                    [("club_id", "in", unused.ids)]
                ).write({"active": False})
                unused.write({"active": False})
        practice.write({"active": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Practice competition removed"),
                "message": _(
                    "The practice competition and its sample clubs were archived."
                ),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _practice_activity_targets(self):
        self.ensure_one()
        matchdays = self.env["federation.matchday"].search(
            [("edition_id", "=", self.id)]
        )
        divisions = self.with_context(active_test=False).tournament_ids
        return list(matchdays) + list(divisions)


class FederationTournamentPractice(models.Model):
    _inherit = "federation.tournament"

    def write(self, values):
        if values.get("website_published") and any(
            self.mapped("edition_id.is_practice")
        ):
            raise ValidationError(
                _(
                    "Divisions of a practice competition cannot be published on the website."
                )
            )
        return super().write(values)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("website_published") and vals.get("edition_id"):
                edition = self.env["federation.competition.edition"].browse(
                    vals["edition_id"]
                )
                if edition.is_practice:
                    raise ValidationError(
                        _(
                            "Divisions of a practice competition cannot be published on the website."
                        )
                    )
        return super().create(vals_list)
