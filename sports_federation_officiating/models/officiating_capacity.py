from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationClubOfficiatingCapacity(models.Model):
    _name = "federation.club.officiating.capacity"
    _description = "Club Officiating Capacity"
    _order = "season_id desc,club_id"

    club_id = fields.Many2one(
        "federation.club", required=True, ondelete="cascade", index=True
    )
    season_id = fields.Many2one(
        "federation.season", required=True, ondelete="cascade", index=True
    )
    max_simultaneous = fields.Integer(
        default=1,
        required=True,
        help="Maximum officials this club can supply at the same time.",
    )
    preparation_minutes = fields.Integer(default=15, required=True)
    rest_minutes = fields.Integer(default=0, required=True)
    travel_minutes = fields.Integer(default=0, required=True)
    qualify_head = fields.Boolean(string="Head referee")
    qualify_assistant = fields.Boolean(string="Assistant referee", default=True)
    qualify_fourth = fields.Boolean(string="Fourth official", default=True)
    qualify_table = fields.Boolean(string="Table official", default=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _club_season_unique = models.Constraint(
        "unique(club_id,season_id)",
        "A club has one officiating-capacity policy per season.",
    )

    @api.constrains(
        "max_simultaneous", "preparation_minutes", "rest_minutes", "travel_minutes"
    )
    def _check_non_negative(self):
        for record in self:
            if (
                record.max_simultaneous < 0
                or min(
                    record.preparation_minutes,
                    record.rest_minutes,
                    record.travel_minutes,
                )
                < 0
            ):
                raise ValidationError(
                    _("Capacity and buffer values cannot be negative.")
                )

    def allocation_policy(self):
        self.ensure_one()
        roles = []
        if self.qualify_head:
            roles.append("head")
        if self.qualify_assistant:
            roles.extend(("assistant_1", "assistant_2"))
        if self.qualify_fourth:
            roles.append("fourth")
        if self.qualify_table:
            roles.append("table")
        return {
            "max_simultaneous": self.max_simultaneous,
            "preparation_minutes": self.preparation_minutes,
            "rest_minutes": self.rest_minutes,
            "travel_minutes": self.travel_minutes,
            "roles": roles,
        }


class FederationScheduleClubDutyPin(models.Model):
    _name = "federation.schedule.club.duty.pin"
    _description = "Pinned Club Duty Allocation"
    _order = "fixture_id,id"

    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="cascade", index=True
    )
    fixture_id = fields.Many2one(
        "federation.fixture", required=True, ondelete="cascade", index=True
    )
    club_id = fields.Many2one(
        "federation.club", required=True, ondelete="restrict", index=True
    )
    reason = fields.Text(required=True)
    pinned_by_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, required=True, readonly=True
    )
    pinned_on = fields.Datetime(
        default=fields.Datetime.now, required=True, readonly=True
    )

    _schedule_fixture_unique = models.Constraint(
        "unique(schedule_id,fixture_id)",
        "A fixture can have only one pinned duty club in a schedule.",
    )

    @api.constrains("schedule_id", "fixture_id", "club_id")
    def _check_scope(self):
        for pin in self:
            if pin.schedule_id.state not in ("draft", "changes_requested"):
                raise ValidationError(_("Pins can be changed only while planning."))
            if pin.fixture_id not in pin.schedule_id.available_fixture_ids:
                raise ValidationError(_("The pinned fixture is outside this schedule."))
            opponents = (
                pin.fixture_id.home_team_id.club_id
                | pin.fixture_id.away_team_id.club_id
            )
            if pin.club_id in opponents:
                raise ValidationError(
                    _("A club cannot be pinned to officiate its own fixture.")
                )


class FederationScheduleCapacityPolicy(models.Model):
    _inherit = "federation.schedule"

    club_duty_pin_ids = fields.One2many(
        "federation.schedule.club.duty.pin", "schedule_id", string="Pinned Club Duties"
    )

    def _club_duty_capacity_policy(self):
        self.ensure_one()
        rows = self.env["federation.club.officiating.capacity"].search(
            [
                ("season_id", "=", self.edition_id.season_id.id),
                ("active", "=", True),
            ]
        )
        return {row.club_id.id: row.allocation_policy() for row in rows}

    def _club_duty_pins(self):
        self.ensure_one()
        return {pin.fixture_id.id: pin.club_id.id for pin in self.club_duty_pin_ids}
