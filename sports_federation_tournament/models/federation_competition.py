from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetition(models.Model):
    _name = "federation.competition"
    _description = "Competition Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(string="Competition Name", required=True, tracking=True)
    code = fields.Char(string="Code", copy=False, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string="Sequence", default=10)
    description = fields.Text(string="Description")
    competition_type = fields.Selection(
        [
            ("league", "League"),
            ("cup", "Cup / Knockout"),
            ("tournament", "Tournament"),
            ("friendly", "Friendly"),
            ("other", "Other"),
        ],
        string="Competition Type",
        default="league",
        required=True,
        tracking=True,
    )
    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Default Rule Set",
        tracking=True,
        ondelete="set null",
        help="Default rule set applied to editions and divisions referencing this competition template.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("closed", "Closed"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    edition_ids = fields.One2many(
        "federation.competition.edition", "competition_id", string="Editions"
    )
    edition_count = fields.Integer(
        string="Edition Count", compute="_compute_edition_count", store=False
    )
    notes = fields.Text(string="Notes")

    _code_unique = models.Constraint(
        "unique (code)", "Competition code must be unique."
    )

    @api.constrains("code")
    def _check_code_unique(self):
        for rec in self:
            if rec.code:
                duplicate = self.search(
                    [("code", "=", rec.code), ("id", "!=", rec.id)],
                    limit=1,
                )
                if duplicate:
                    raise ValidationError(
                        _("Competition code '%(code)s' is already in use.", code=rec.code)
                    )

    def _raise_if_duplicate_code(self, code, exclude_id=None):
        """Pre-insert/write check that raises ValidationError before DB constraint fires."""
        if not code:
            return
        domain = [("code", "=", code)]
        if exclude_id:
            domain.append(("id", "!=", exclude_id))
        if self.search(domain, limit=1):
            raise ValidationError(
                _("Competition code '%(code)s' is already in use.", code=code)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._raise_if_duplicate_code(vals.get("code"))
        return super().create(vals_list)

    def write(self, vals):
        if "code" in vals:
            for rec in self:
                self._raise_if_duplicate_code(vals["code"], exclude_id=rec.id)
        return super().write(vals)

    @api.depends("edition_ids")
    def _compute_edition_count(self):
        """Compute edition count."""
        for rec in self:
            rec.edition_count = len(rec.edition_ids)

    def action_activate(self):
        """Execute the activate action."""
        for rec in self:
            rec.state = "active"

    def action_close(self):
        """Execute the close action."""
        for rec in self:
            rec.state = "closed"

    def action_draft(self):
        """Execute the draft action."""
        for rec in self:
            rec.state = "draft"

    def action_view_editions(self):
        """Execute the view editions action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_competition_edition_action"
        )
        action["domain"] = [("competition_id", "=", self.id)]
        return action
