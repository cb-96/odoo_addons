from odoo import _, api, fields, models


class FederationRoundAssignWizard(models.TransientModel):
    _name = "federation.round.assign.wizard"
    _description = "Assign Official to Round"

    round_id = fields.Many2one(
        "federation.tournament.round",
        string="Round",
        required=True,
    )
    role = fields.Selection(
        [
            ("head", "Head Referee"),
            ("assistant_1", "Assistant Referee 1"),
            ("assistant_2", "Assistant Referee 2"),
            ("fourth", "Fourth Official"),
            ("table", "Table Official"),
        ],
        string="Role",
        required=True,
        default="head",
    )
    referee_id = fields.Many2one(
        "federation.referee",
        string="Referee",
        required=True,
    )
    matches_total = fields.Integer(
        string="Matches in Round",
        compute="_compute_preview",
    )
    matches_to_assign = fields.Integer(
        string="Will Assign",
        compute="_compute_preview",
    )
    matches_skipped = fields.Integer(
        string="Already Assigned (skipped)",
        compute="_compute_preview",
    )

    @api.depends("round_id", "role")
    def _compute_preview(self):
        for rec in self:
            if not rec.round_id or not rec.role:
                rec.matches_total = 0
                rec.matches_to_assign = 0
                rec.matches_skipped = 0
                continue
            active_matches = rec.round_id.match_ids.filtered(
                lambda m: m.state != "cancelled"
            )
            already = self.env["federation.match.referee"].search(
                [
                    ("match_id", "in", active_matches.ids),
                    ("role", "=", rec.role),
                    ("state", "!=", "cancelled"),
                ]
            )
            already_match_ids = set(already.mapped("match_id").ids)
            rec.matches_total = len(active_matches)
            rec.matches_skipped = len(already_match_ids)
            rec.matches_to_assign = len(active_matches) - len(already_match_ids)

    def action_apply(self):
        """Create one assignment per active match in the round, skipping already-assigned roles."""
        self.ensure_one()
        active_matches = self.round_id.match_ids.filtered(
            lambda m: m.state != "cancelled"
        )
        already = self.env["federation.match.referee"].search(
            [
                ("match_id", "in", active_matches.ids),
                ("role", "=", self.role),
                ("state", "!=", "cancelled"),
            ]
        )
        already_match_ids = {r.match_id.id for r in already}
        vals_list = [
            {
                "match_id": match.id,
                "referee_id": self.referee_id.id,
                "role": self.role,
            }
            for match in active_matches
            if match.id not in already_match_ids
        ]
        if vals_list:
            self.env["federation.match.referee"].create(vals_list)
        return {"type": "ir.actions.act_window_close"}
