from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ROLE_SELECTION = [
    ("head", "Head Referee"),
    ("assistant_1", "Assistant Referee 1"),
    ("assistant_2", "Assistant Referee 2"),
    ("fourth", "Fourth Official"),
    ("table", "Table Official"),
]


class FederationMatchdayAssignOfficialWizard(models.TransientModel):
    _name = "federation.matchday.assign.official.wizard"
    _description = "Assign Officials to Published Match Day"

    matchday_id = fields.Many2one(
        "federation.matchday",
        required=True,
        domain="[('current_publication_id.state','=','live')]",
    )
    assignment_type = fields.Selection(
        [("referee", "Federation Referee"), ("club", "Club Duty")],
        required=True,
        default="referee",
    )
    role = fields.Selection(ROLE_SELECTION, required=True, default="head")
    referee_id = fields.Many2one("federation.referee")
    club_id = fields.Many2one("federation.club")
    open_duties = fields.Boolean(
        default=True,
        help="Immediately open generated club duties for nomination.",
    )
    matches_total = fields.Integer(compute="_compute_preview")
    matches_to_assign = fields.Integer(compute="_compute_preview")
    matches_skipped = fields.Integer(compute="_compute_preview")

    def _published_matches(self):
        self.ensure_one()
        publication = self.matchday_id.current_publication_id
        if not publication or publication.state != "live":
            return self.env["federation.match"]
        return self.env["federation.match"].search(
            [
                ("schedule_publication_id", "=", publication.id),
                ("logical_fixture_id", "!=", False),
                ("state", "!=", "cancelled"),
            ],
            order="date_scheduled,id",
        )

    @api.depends("matchday_id", "assignment_type", "role", "referee_id", "club_id")
    def _compute_preview(self):
        for wizard in self:
            if not wizard.matchday_id or not wizard.role:
                wizard.matches_total = wizard.matches_to_assign = 0
                wizard.matches_skipped = 0
                continue
            matches = wizard._published_matches()
            if wizard.assignment_type == "referee":
                existing = self.env["federation.match.referee"].search(
                    [
                        ("match_id", "in", matches.ids),
                        ("role", "=", wizard.role),
                        ("state", "!=", "cancelled"),
                    ]
                )
            else:
                existing = self.env["federation.match.club.referee.duty"].search(
                    [
                        ("match_id", "in", matches.ids),
                        ("role", "=", wizard.role),
                        ("club_id", "=", wizard.club_id.id),
                    ]
                )
            skipped = len(existing.mapped("match_id"))
            wizard.matches_total = len(matches)
            wizard.matches_skipped = skipped
            wizard.matches_to_assign = len(matches) - skipped

    def action_apply(self):
        self.ensure_one()
        matches = self._published_matches()
        if not matches:
            raise ValidationError(
                _("The live publication contains no assignable matches.")
            )
        if self.assignment_type == "referee" and not self.referee_id:
            raise ValidationError(_("Select a federation referee."))
        if self.assignment_type == "club" and not self.club_id:
            raise ValidationError(_("Select the club responsible for the duty."))
        if self.assignment_type == "referee":
            Model = self.env["federation.match.referee"]
            existing_ids = set(
                Model.search(
                    [
                        ("match_id", "in", matches.ids),
                        ("role", "=", self.role),
                        ("state", "!=", "cancelled"),
                    ]
                )
                .mapped("match_id")
                .ids
            )
            values = [
                {
                    "match_id": match.id,
                    "referee_id": self.referee_id.id,
                    "role": self.role,
                }
                for match in matches
                if match.id not in existing_ids
            ]
            if values:
                Model.create(values)
        else:
            Model = self.env["federation.match.club.referee.duty"]
            existing_ids = set(
                Model.search(
                    [
                        ("match_id", "in", matches.ids),
                        ("role", "=", self.role),
                        ("club_id", "=", self.club_id.id),
                    ]
                )
                .mapped("match_id")
                .ids
            )
            duties = Model.create(
                [
                    {
                        "match_id": match.id,
                        "club_id": self.club_id.id,
                        "role": self.role,
                    }
                    for match in matches
                    if match.id not in existing_ids
                ]
            )
            if self.open_duties:
                duties.action_open()
        return {"type": "ir.actions.act_window_close"}
