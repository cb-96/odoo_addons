from odoo import _, api, models
from odoo.exceptions import ValidationError


class DivisionBoundary(models.Model):
    _inherit = "federation.tournament"

    @api.model
    def _edition_scope_values(self, values, creating=False):
        values = dict(values)
        if values.get("edition_id"):
            edition = (
                self.env["federation.competition.edition"]
                .browse(values["edition_id"])
                .exists()
            )
            if not edition:
                raise ValidationError(_("Choose an existing competition edition."))
            edition.check_access("read")
            for field, expected in (
                ("season_id", edition.season_id.id),
                ("competition_id", edition.competition_id.id),
            ):
                if field in values and values[field] != expected:
                    raise ValidationError(
                        _("Division competition and season must match its edition.")
                    )
                values[field] = expected
            if not values.get("rule_set_id") and edition.rule_set_id:
                values.setdefault("rule_set_id", edition.rule_set_id.id)
            if creating and not values.get("date_start"):
                values.setdefault(
                    "date_start", edition.date_start or edition.season_id.date_start
                )
        return values

    @api.model_create_multi
    def create(self, vals_list):
        default_edition = self.default_get(["edition_id"]).get("edition_id")
        normalized = []
        for values in vals_list:
            values = dict(values)
            if "edition_id" not in values and default_edition:
                values["edition_id"] = default_edition
            normalized.append(self._edition_scope_values(values, creating=True))
        return super().create(normalized)

    def write(self, vals):
        if vals.get("edition_id"):
            if any(
                division.edition_id and division.edition_id.id != vals["edition_id"]
                for division in self
            ):
                raise ValidationError(
                    _(
                        "An existing division cannot move to another edition. Create a new division instead."
                    )
                )
            vals = self._edition_scope_values(vals)
        elif "edition_id" in vals and self.filtered("edition_id"):
            raise ValidationError(
                _(
                    "A division cannot be detached from its competition edition. Archive it instead."
                )
            )
        return super().write(vals)

    @api.constrains("edition_id", "competition_id", "season_id")
    def _check_edition_scope(self):
        for division in self.filtered("edition_id"):
            if (
                division.competition_id != division.edition_id.competition_id
                or division.season_id != division.edition_id.season_id
            ):
                raise ValidationError(
                    _("Division competition and season must match its edition.")
                )

    def action_open_competition_edition(self):
        self.ensure_one()
        self.check_access("read")
        if not self.edition_id:
            raise ValidationError(
                _(
                    "This is a legacy standalone tournament; review its competition mapping first."
                )
            )
        return self.edition_id.get_formview_action()

    def action_open_division_game_days(self):
        self.ensure_one()
        self.check_access("read")
        if not self.edition_id or self.env.get("federation.matchday") is None:
            raise ValidationError(
                _(
                    "Game-day planning requires a competition edition and the scheduling addon."
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Competition Game Days"),
            "res_model": "federation.matchday",
            "view_mode": "list,form",
            "domain": [("edition_id", "=", self.edition_id.id)],
            "context": {"default_edition_id": self.edition_id.id},
        }


class EditionIdentityBoundary(models.Model):
    _inherit = "federation.competition.edition"

    def write(self, vals):
        changed = self.filtered(
            lambda edition: any(
                field in vals and vals[field] != edition[field].id
                for field in ("competition_id", "season_id")
            )
        )
        if changed and self.env["federation.tournament"].sudo().search_count(
            [
                ("edition_id", "in", changed.ids),
            ]
        ):
            raise ValidationError(
                _(
                    "An edition with divisions cannot change competition or season. Create another edition instead."
                )
            )
        return super().write(vals)
