from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sports_federation_base.batch_jobs import process_each


class FederationSuspension(models.Model):
    _name = "federation.suspension"
    _description = "Suspension"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(required=True)
    case_id = fields.Many2one(
        "federation.disciplinary.case",
        string="Case",
        required=True,
        ondelete="cascade",
        index=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        required=True,
        ondelete="restrict",
        index=True,
    )
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(
        string="End Date",
        help="Last day of the suspension. Leave empty for a suspension of a "
        "number of matches.",
    )
    match_count = fields.Integer(
        string="Matches to Serve",
        help="Suspension ends after the player's teams finished this many matches "
        "from the start date. 0 means the suspension runs by date only.",
    )
    matches_served = fields.Integer(
        compute="_compute_matches_served",
        string="Matches Served",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Upcoming"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    notes = fields.Text(string="Notes")

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for record in self:
            if record.date_end and record.date_start:
                if record.date_end < record.date_start:
                    raise ValidationError("End date must be on or after start date.")

    @api.constrains("date_end", "match_count")
    def _check_duration(self):
        for record in self:
            if record.match_count < 0:
                raise ValidationError("The number of matches cannot be negative.")
            if not record.date_end and not record.match_count:
                raise ValidationError(
                    "Set an end date or a number of matches to serve."
                )

    def _served_matches(self):
        """Finished matches of the player's teams since the start date."""
        self.ensure_one()
        teams = self.player_id.team_ids
        if not teams or not self.date_start:
            return self.env["federation.match"]
        start = fields.Datetime.to_datetime(self.date_start)
        return (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("state", "=", "done"),
                    ("date_scheduled", ">=", start),
                    "|",
                    ("home_team_id", "in", teams.ids),
                    ("away_team_id", "in", teams.ids),
                ]
            )
        )

    def _compute_matches_served(self):
        for record in self:
            record.matches_served = (
                len(record._served_matches()) if record.match_count else 0
            )

    def _is_served(self, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        if self.date_end and self.date_end < today:
            return True
        return bool(self.match_count) and self.matches_served >= self.match_count

    def action_activate(self):
        """Activate the suspension; it affects eligibility from its start date."""
        records_to_activate = self.filtered(
            lambda record: record.state not in ("active", "scheduled")
        )
        if not records_to_activate:
            return

        today = fields.Date.context_today(self)
        upcoming = records_to_activate.filtered(
            lambda record: record.date_start > today
        )
        started = records_to_activate - upcoming
        upcoming.write({"state": "scheduled"})
        started.write({"state": "active"})

        for record in started:
            record.player_id.action_suspend()

        dispatcher = self.env.get("federation.notification.dispatcher")
        if dispatcher is not None:
            for record in records_to_activate:
                dispatcher.send_suspension_issued(record)

    def action_cancel(self):
        """Cancel the suspension and restore the player's state if no other active suspensions remain."""
        for record in self:
            record.state = "cancelled"
            record._maybe_restore_player_state()

    @api.model
    def _cron_update_suspensions(self):
        """Start upcoming suspensions and end served ones (daily job).

        Each suspension is handled on its own: one that cannot start or end
        (for example a player record that fails validation) is logged and the
        others still change state.
        """
        today = fields.Date.context_today(self)
        due = self.search([("state", "=", "scheduled"), ("date_start", "<=", today)])
        process_each(
            due, lambda record: record._start_scheduled(), label="Start suspension"
        )
        active = self.search([("state", "=", "active")])
        process_each(
            active.filtered(lambda record: record._is_served(today)),
            lambda record: record.action_expire(),
            label="End served suspension",
        )
        return True

    def _start_scheduled(self):
        self.ensure_one()
        self.write({"state": "active"})
        self.player_id.action_suspend()

    def _expire_served_by_matches(self, teams):
        """Called when a match finishes: end match-count suspensions served."""
        candidates = self.search(
            [
                ("state", "=", "active"),
                ("match_count", ">", 0),
                ("player_id.team_ids", "in", teams.ids),
            ]
        )
        candidates.filtered(lambda record: record._is_served()).action_expire()
        return True

    def action_expire(self):
        """Mark the suspension as expired and restore the player's state if eligible."""
        records_to_expire = self.filtered(lambda record: record.state == "active")
        records_to_expire.write({"state": "expired"})
        for record in records_to_expire:
            record._maybe_restore_player_state()

    def _maybe_restore_player_state(self):
        """Restore the player to active if they have no remaining active suspensions."""
        self.ensure_one()
        player = self.player_id
        active_suspensions = self.env["federation.suspension"].search(
            [
                ("player_id", "=", player.id),
                ("state", "=", "active"),
                ("id", "!=", self.id),
            ],
            limit=1,
        )
        if not active_suspensions:
            player.action_activate()
