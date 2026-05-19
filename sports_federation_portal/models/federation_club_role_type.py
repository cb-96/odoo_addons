from odoo import api, fields, models


class FederationClubRoleType(models.Model):
    """Configurable role types for club representatives.

    This model allows federation administrators to define custom role types
    for club representatives (e.g., competition contact, finance contact,
    safeguarding contact, president, secretary, admin, other).
    """

    _name = "federation.club.role.type"
    _description = "Club Role Type"
    _order = "sequence, name"

    name = fields.Char(string="Role Name", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        copy=False,
        help="Unique code for this role type, used for programmatic access.",
    )
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string="Description", translate=True)
    is_primary = fields.Boolean(
        string="Is Primary Contact",
        default=False,
        help="If checked, this role type represents a primary contact role. "
        "Only one representative per club can be primary for each role type.",
    )
    is_competition_contact = fields.Boolean(
        string="Competition Contact",
        default=False,
        help="This role is responsible for competition-related matters.",
    )
    is_finance_contact = fields.Boolean(
        string="Finance Contact",
        default=False,
        help="This role is responsible for financial matters.",
    )
    is_safeguarding_contact = fields.Boolean(
        string="Safeguarding Contact",
        default=False,
        help="This role is responsible for safeguarding matters.",
    )
    team_scoped = fields.Boolean(
        string="Team Scoped",
        default=False,
        help="Use this role for staff assigned to a specific team rather than a whole club.",
    )

    _code_unique = models.Constraint("UNIQUE(code)", "Role type code must be unique.")

    @api.model
    def _get_default_role_types(self):
        """Return default role type codes for data initialization."""
        return [
            "competition_contact",
            "finance_contact",
            "safeguarding_contact",
            "coach",
            "team_manager",
            "president",
            "secretary",
            "admin",
            "other",
        ]

    @api.model
    def get_by_code(self, code):
        """Return the role type record for the given code, or empty recordset."""
        return self.search([("code", "=", code)], limit=1)
