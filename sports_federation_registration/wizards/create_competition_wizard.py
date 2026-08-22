from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCreateCompetitionWizard(models.TransientModel):
    _name = "federation.create.competition.wizard"
    _description = "Create Competition Workflow"
    competition_id = fields.Many2one(
        "federation.competition", required=True, string="Competition Template"
    )
    name = fields.Char(required=True)
    season_id = fields.Many2one("federation.season", required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date()
    rule_set_id = fields.Many2one("federation.rule.set")
    registration_open = fields.Datetime()
    registration_close = fields.Datetime()
    division_line_ids = fields.One2many(
        "federation.create.competition.division.wizard", "wizard_id", string="Divisions"
    )
    role_line_ids = fields.One2many(
        "federation.create.competition.role.wizard",
        "wizard_id",
        string="Responsibilities",
    )

    @api.onchange("competition_id")
    def _onchange_competition(self):
        if self.competition_id:
            self.rule_set_id = self.competition_id.rule_set_id
            if not self.name and self.season_id:
                self.name = f"{self.competition_id.name} - {self.season_id.name}"

    @api.constrains("date_start", "date_end", "registration_open", "registration_close")
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(
                    _("The competition end date cannot precede its start date.")
                )
            if (
                rec.registration_open
                and rec.registration_close
                and rec.registration_close <= rec.registration_open
            ):
                raise ValidationError(_("Registration must close after it opens."))

    def action_create_competition(self):
        self.ensure_one()
        if not self.division_line_ids:
            raise ValidationError(_("Add at least one division."))
        edition = self.env["federation.competition.edition"].create(
            {
                "name": self.name,
                "competition_id": self.competition_id.id,
                "season_id": self.season_id.id,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "rule_set_id": self.rule_set_id.id,
                "engine_state": "draft",
            }
        )
        for line in self.division_line_ids:
            division = self.env["federation.tournament"].create(
                {
                    "name": line.name,
                    "code": line.code or False,
                    "edition_id": edition.id,
                    "competition_id": self.competition_id.id,
                    "season_id": self.season_id.id,
                    "rule_set_id": self.rule_set_id.id,
                    "date_start": self.date_start,
                    "date_end": self.date_end,
                    "category": line.category or False,
                    "gender": line.gender or False,
                    "tournament_type": line.tournament_type,
                }
            )
            self.env["federation.registration.window"].create(
                {
                    "name": _("Registration - %(division)s", division=division.name),
                    "edition_id": edition.id,
                    "division_id": division.id,
                    "date_open": self.registration_open,
                    "date_close": self.registration_close,
                }
            )
        for line in self.role_line_ids.filtered("user_id"):
            self.env["federation.competition.role.assignment"].create(
                {
                    "edition_id": edition.id,
                    "role": line.role,
                    "user_id": line.user_id.id,
                }
            )
        self.env["federation.competition.event"].emit(
            edition,
            "competition_workflow_created",
            {"division_count": len(self.division_line_ids)},
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "federation.competition.edition",
            "res_id": edition.id,
            "view_mode": "form",
            "target": "current",
        }


class FederationCreateCompetitionDivisionWizard(models.TransientModel):
    _name = "federation.create.competition.division.wizard"
    _description = "Competition Division Setup"
    wizard_id = fields.Many2one(
        "federation.create.competition.wizard", required=True, ondelete="cascade"
    )
    name = fields.Char(required=True)
    code = fields.Char()
    category = fields.Selection(
        [
            ("senior", "Senior"),
            ("youth", "Youth"),
            ("junior", "Junior"),
            ("cadet", "Cadet"),
            ("mini", "Mini"),
        ]
    )
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("mixed", "Mixed")]
    )
    tournament_type = fields.Selection(
        [("single_day", "Single Day"), ("multi_day", "Multi Day")],
        default="multi_day",
        required=True,
    )


class FederationCreateCompetitionRoleWizard(models.TransientModel):
    _name = "federation.create.competition.role.wizard"
    _description = "Competition Responsibility Setup"
    wizard_id = fields.Many2one(
        "federation.create.competition.wizard", required=True, ondelete="cascade"
    )
    role = fields.Selection(
        selection=lambda self: self.env["federation.competition.role.assignment"]
        ._fields["role"]
        .selection,
        required=True,
    )
    user_id = fields.Many2one("res.users", required=True)
