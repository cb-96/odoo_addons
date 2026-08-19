from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationRuleSet(models.Model):
    _name = "federation.rule.set"
    _description = "Federation Rule Set"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Rule Set Name", required=True, tracking=True)
    code = fields.Char(string="Code", copy=False, tracking=True)
    active = fields.Boolean(default=True)
    description = fields.Text(string="Description")
    locked = fields.Boolean(default=False, copy=False, tracking=True)
    locked_on = fields.Datetime(copy=False, readonly=True)
    locked_by_id = fields.Many2one("res.users", copy=False, readonly=True)

    # Points configuration
    points_rule_ids = fields.One2many(
        "federation.points.rule", "rule_set_id", string="Points Rules"
    )
    points_win = fields.Integer(
        string="Points for Win",
        default=3,
        tracking=True,
        help="Default points awarded for a win. Overridden by explicit points rules if present.",
    )
    points_draw = fields.Integer(
        string="Points for Draw",
        default=1,
        tracking=True,
        help="Default points awarded for a draw.",
    )
    points_loss = fields.Integer(
        string="Points for Loss",
        default=0,
        tracking=True,
        help="Default points awarded for a loss.",
    )

    # Tie-break configuration
    tie_break_rule_ids = fields.One2many(
        "federation.tie_break.rule", "rule_set_id", string="Tie-Break Rules"
    )

    # Squad configuration
    squad_min_size = fields.Integer(
        string="Min Squad Size",
        default=0,
        tracking=True,
        help="Minimum number of players required. 0 means no minimum enforced.",
    )
    squad_max_size = fields.Integer(
        string="Max Squad Size",
        default=0,
        tracking=True,
        help="Maximum number of players allowed. 0 means no maximum enforced.",
    )

    # Referee configuration
    referee_required_count = fields.Integer(
        string="Required Referee Count",
        default=0,
        tracking=True,
        help="Number of referees required per match. 0 means no requirement.",
    )

    # Seeding configuration
    seeding_mode = fields.Selection(
        [
            ("none", "No Seeding"),
            ("manual", "Manual Seeding"),
            ("ranking", "By Federation Ranking"),
            ("random", "Random"),
        ],
        string="Seeding Mode",
        default="none",
        required=True,
        tracking=True,
    )

    # Eligibility
    eligibility_rule_ids = fields.One2many(
        "federation.eligibility.rule", "rule_set_id", string="Eligibility Rules"
    )

    # Qualification
    qualification_rule_ids = fields.One2many(
        "federation.qualification.rule", "rule_set_id", string="Qualification Rules"
    )

    _code_unique = models.Constraint("unique (code)", "Rule set code must be unique.")

    _LOCKED_FIELDS = {"points_win", "points_draw", "points_loss", "squad_min_size", "squad_max_size", "referee_required_count", "seeding_mode", "points_rule_ids", "tie_break_rule_ids", "eligibility_rule_ids", "qualification_rule_ids"}

    def write(self, vals):
        if self.filtered("locked") and self._LOCKED_FIELDS.intersection(vals):
            raise ValidationError("Locked rule sets cannot be changed. Duplicate the rule set instead.")
        return super().write(vals)

    def action_lock(self):
        self.filtered(lambda r: not r.locked).write({"locked": True, "locked_on": fields.Datetime.now(), "locked_by_id": self.env.user.id})
        return True

    def action_unlock(self):
        if not self.env.user.has_group("sports_federation_base.group_federation_manager"):
            raise ValidationError("Only federation managers can unlock rule sets.")
        self.write({"locked": False, "locked_on": False, "locked_by_id": False})
        return True

    @api.constrains("squad_min_size", "squad_max_size")
    def _check_squad_sizes(self):
        """Validate squad sizes."""
        for rec in self:
            if (
                rec.squad_min_size > 0
                and rec.squad_max_size > 0
                and rec.squad_min_size > rec.squad_max_size
            ):
                raise ValidationError(
                    "Minimum squad size cannot exceed maximum squad size."
                )
