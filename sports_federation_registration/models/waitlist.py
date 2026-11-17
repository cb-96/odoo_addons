from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationRegistrationCapacity(models.Model):
    _inherit = "federation.registration.window"

    team_capacity = fields.Integer(
        default=0, help="Zero means no configured capacity limit."
    )
    offer_valid_hours = fields.Integer(default=72, required=True)
    next_waitlist_sequence = fields.Integer(default=1, required=True, copy=False)
    offer_ids = fields.One2many(
        "federation.registration.offer", "window_id", readonly=True
    )
    waitlist_count = fields.Integer(compute="_compute_capacity_counts")
    reserved_count = fields.Integer(compute="_compute_capacity_counts")
    approved_count = fields.Integer(compute="_compute_capacity_counts")

    @api.depends("entry_ids.state", "offer_ids.state")
    def _compute_capacity_counts(self):
        for window in self:
            window.waitlist_count = len(
                window.entry_ids.filtered(lambda item: item.state == "waitlisted")
            )
            window.reserved_count = len(
                window.offer_ids.filtered(lambda item: item.state == "offered")
            )
            window.approved_count = len(
                window.entry_ids.filtered(lambda item: item.state == "approved")
            )

    @api.constrains("team_capacity", "offer_valid_hours")
    def _check_capacity(self):
        for window in self:
            if window.team_capacity < 0 or window.offer_valid_hours <= 0:
                raise ValidationError(
                    _("Capacity cannot be negative and offer time must be positive.")
                )

    def _capacity_lock(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM federation_registration_window WHERE id=%s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        self.entry_ids.invalidate_recordset()
        self.offer_ids.invalidate_recordset()

    def _places_used(self):
        self.ensure_one()
        return len(
            self.entry_ids.filtered(lambda item: item.state in ("approved", "offered"))
        )

    def _queue_entry(self, entry):
        self.ensure_one()
        if not entry.waitlist_sequence:
            entry.write({"waitlist_sequence": self.next_waitlist_sequence})
            self.write({"next_waitlist_sequence": self.next_waitlist_sequence + 1})
        entry.write({"state": "waitlisted"})
        return False

    def _admit_or_waitlist(self, entry):
        self.ensure_one()
        self._capacity_lock()
        if entry.window_id != self:
            raise ValidationError(_("Entry is outside this registration window."))
        queue_ahead = self.entry_ids.filtered(
            lambda item: item != entry
            and item.state in ("waitlisted", "offered")
            and (
                not entry.waitlist_sequence
                or item.waitlist_sequence < entry.waitlist_sequence
            )
        )
        full = bool(self.team_capacity and self._places_used() >= self.team_capacity)
        if full or queue_ahead:
            return self._queue_entry(entry)
        entry.write({"state": "approved"})
        return True

    def action_offer_next(self):
        self.ensure_one()
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id, "registration_manager", "competition_director"
        )
        self._capacity_lock()
        if self.team_capacity and self._places_used() >= self.team_capacity:
            raise ValidationError(_("No unreserved place is available."))
        entry = self.entry_ids.filtered(lambda item: item.state == "waitlisted").sorted(
            lambda item: (item.waitlist_sequence, item.id)
        )[:1]
        if not entry:
            raise ValidationError(_("The waiting list is empty."))
        expires = fields.Datetime.now() + timedelta(hours=self.offer_valid_hours)
        offer = self.env["federation.registration.offer"].create(
            {"entry_id": entry.id, "expires_on": expires}
        )
        entry.write({"state": "offered"})
        return offer.get_formview_action()

    def materialize_direct_team_selection(self, teams):
        for window in self:
            queued = window.entry_ids.filtered(
                lambda item: item.state in ("waitlisted", "offered")
            )
            if window.team_capacity and len(teams) > window.team_capacity:
                raise ValidationError(_("The selected teams exceed division capacity."))
            if queued and any(team not in queued.team_id for team in teams):
                raise ValidationError(
                    _(
                        "A waiting list or reserved offer is active. Use the offer "
                        "workflow so a new selection cannot jump the queue."
                    )
                )
        return super().materialize_direct_team_selection(teams)


class FederationCompetitionEntryCapacity(models.Model):
    _inherit = "federation.competition.entry"

    state = fields.Selection(
        selection_add=[
            ("changes_requested", "Changes Requested"),
            ("waitlisted", "Waiting List"),
            ("offered", "Place Offered"),
            ("offer_expired", "Offer Expired"),
        ],
        ondelete={
            "changes_requested": "set default",
            "waitlisted": "set default",
            "offered": "set default",
            "offer_expired": "set default",
        },
    )
    waitlist_sequence = fields.Integer(readonly=True, copy=False, index=True)
    offer_ids = fields.One2many(
        "federation.registration.offer", "entry_id", readonly=True
    )

    def action_submit(self):
        invalid = self.filtered(
            lambda entry: entry.state
            not in (
                "draft",
                "changes_requested",
                "rejected",
                "withdrawn",
                "offer_expired",
            )
        )
        if invalid:
            raise ValidationError(
                _("This entry cannot be submitted from its current state.")
            )
        self.write(
            {
                "state": "submitted",
                "submitted_by_id": self.env.user.id,
                "submitted_on": fields.Datetime.now(),
                "reviewed_by_id": False,
                "reviewed_on": False,
            }
        )
        for entry in self.filtered(
            lambda item: not item.edition_id.registration_approval_required
        ):
            entry.write(
                {
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_on": fields.Datetime.now(),
                    "review_note": _("Automatically reviewed by competition policy."),
                }
            )
            entry.window_id._admit_or_waitlist(entry)
        return True

    def action_approve(self):
        for entry in self:
            self.env["federation.competition.role.assignment"].assert_role(
                entry.edition_id, "registration_manager", "competition_director"
            )
            if entry.state != "submitted":
                raise ValidationError(_("Only submitted entries can be reviewed."))
            entry.write(
                {
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_on": fields.Datetime.now(),
                }
            )
            entry.window_id._admit_or_waitlist(entry)
        return True

    def action_return(self, reason):
        if not (reason or "").strip():
            raise ValidationError(_("A review reason is required."))
        self.write(
            {
                "state": "changes_requested",
                "review_note": reason.strip(),
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            }
        )
        return True

    def action_requeue(self):
        for entry in self:
            if entry.state != "offer_expired":
                raise ValidationError(_("Only an expired offer can rejoin the queue."))
            window = entry.window_id
            window._capacity_lock()
            entry.write(
                {
                    "waitlist_sequence": window.next_waitlist_sequence,
                    "state": "waitlisted",
                }
            )
            window.write({"next_waitlist_sequence": window.next_waitlist_sequence + 1})
        return True


class FederationRegistrationOffer(models.Model):
    _name = "federation.registration.offer"
    _description = "Reserved Registration Place"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    entry_id = fields.Many2one(
        "federation.competition.entry", required=True, ondelete="restrict", index=True
    )
    window_id = fields.Many2one(
        related="entry_id.window_id", store=True, index=True, readonly=True
    )
    team_id = fields.Many2one(
        related="entry_id.team_id", store=True, index=True, readonly=True
    )
    state = fields.Selection(
        [
            ("offered", "Offered"),
            ("accepted", "Accepted"),
            ("expired", "Expired"),
            ("released", "Released"),
        ],
        default="offered",
        required=True,
        tracking=True,
        index=True,
    )
    offered_on = fields.Datetime(
        default=fields.Datetime.now, required=True, readonly=True
    )
    expires_on = fields.Datetime(required=True, index=True)
    accepted_on = fields.Datetime(readonly=True)
    released_on = fields.Datetime(readonly=True)
    release_reason = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            entry = self.env["federation.competition.entry"].browse(
                values.get("entry_id")
            )
            if not entry:
                raise ValidationError(_("A reserved offer requires an entry."))
            self.env["federation.competition.role.assignment"].assert_role(
                entry.edition_id, "registration_manager", "competition_director"
            )
        return super().create(vals_list)

    def _lock(self):
        for window in self.mapped("window_id"):
            window._capacity_lock()
        self.env.cr.execute(
            "SELECT id FROM federation_registration_offer "
            "WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(self.ids)],
        )
        self.invalidate_recordset()

    def action_accept(self):
        self._lock()
        for offer in self:
            if offer.state != "offered" or offer.expires_on <= fields.Datetime.now():
                raise ValidationError(_("This reserved offer is no longer current."))
            if offer.entry_id.state != "offered":
                raise ValidationError(_("The entry no longer owns this reservation."))
            offer.write({"state": "accepted", "accepted_on": fields.Datetime.now()})
            offer.entry_id.write({"state": "approved"})
        return True

    def action_release(self, reason=False):
        self._lock()
        for offer in self:
            if offer.state != "offered":
                raise ValidationError(_("Only a current offer can be released."))
            offer.write(
                {
                    "state": "released",
                    "released_on": fields.Datetime.now(),
                    "release_reason": reason or _("Released by operator."),
                }
            )
            offer.entry_id.write({"state": "offer_expired"})
        return True

    @api.model
    def _cron_expire(self):
        now = fields.Datetime.now()
        for offer in self.sudo().search(
            [("state", "=", "offered"), ("expires_on", "<=", now)], limit=500
        ):
            with self.env.cr.savepoint():
                offer._lock()
                if offer.state == "offered" and offer.expires_on <= now:
                    offer.write(
                        {
                            "state": "expired",
                            "released_on": now,
                            "release_reason": _("Offer expired."),
                        }
                    )
                    offer.entry_id.write({"state": "offer_expired"})
        return True
