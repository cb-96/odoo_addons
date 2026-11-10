from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationClubSeasonRegistration(models.Model):
    """Annual club player pool. Licences remain the canonical player records."""

    _name = "federation.club.season.registration"
    _description = "Club Season Player Registration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "season_id desc, club_id"

    name = fields.Char(compute="_compute_name", store=True)
    club_id = fields.Many2one("federation.club", required=True, ondelete="restrict")
    season_id = fields.Many2one(
        "federation.season", required=True, ondelete="restrict",
        default=lambda self: self.env["federation.season"]._default_registration_season(),
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    season_date_start = fields.Date(related="season_id.date_start")
    season_date_end = fields.Date(related="season_id.date_end")
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"),
         ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True,
    )
    license_ids = fields.One2many(
        "federation.player.license", "club_registration_id", string="Season Players",
    )
    player_count = fields.Integer(compute="_compute_counts")
    registered_player_count = fields.Integer(compute="_compute_counts")
    pending_player_count = fields.Integer(compute="_compute_counts")
    notes = fields.Text()

    _club_season_unique = models.Constraint(
        "unique (club_id, season_id)", "A club already has a registration for this season.",
    )

    @api.depends("club_id.name", "season_id.name")
    def _compute_name(self):
        for registration in self:
            registration.name = "%s / %s" % (
                registration.club_id.display_name, registration.season_id.display_name,
            )

    @api.depends("license_ids", "license_ids.state")
    def _compute_counts(self):
        for registration in self:
            registration.player_count = len(registration.license_ids)
            registration.registered_player_count = len(
                registration.license_ids.filtered(lambda item: item.state == "active")
            )
            registration.pending_player_count = len(
                registration.license_ids.filtered(lambda item: item.state == "draft")
            )

    @api.model
    def _get_or_create(self, club, season):
        """Serialize concurrent club submissions using the unique scope key."""
        domain = [("club_id", "=", club.id), ("season_id", "=", season.id)]
        registration = self.search(domain, limit=1)
        if registration:
            return registration
        try:
            with self.env.cr.savepoint():
                return self.create({"club_id": club.id, "season_id": season.id})
        except IntegrityError:
            registration = self.search(domain, limit=1)
            if not registration:
                raise
            return registration

    def write(self, vals):
        self._registration_lock()
        if any(item.state == "cancelled" for item in self) and vals.get("state", "cancelled") != "cancelled":
            raise ValidationError(_("Cancelled club registrations cannot be reopened implicitly."))
        changed_scope = any(
            key in vals and vals[key] != item[key].id
            for item in self for key in ("club_id", "season_id")
        )
        if changed_scope and self.mapped("license_ids"):
            raise ValidationError(_("A registration with players cannot change club or season."))
        if vals.get("state") == "cancelled" and self.mapped("license_ids").filtered(
            lambda item: item.state in ("draft", "active")
        ):
            raise ValidationError(_("Cancel the player licences before cancelling their club registration."))
        return super().write(vals)

    def unlink(self):
        if self.mapped("license_ids") or any(item.state != "draft" for item in self):
            raise ValidationError(_("Keep season registration history; cancel it instead."))
        return super().unlink()

    def _assert_open(self):
        if any(item.season_id.state != "open" for item in self):
            raise ValidationError(_("Player registration requires an open season."))
        if any(item.state == "cancelled" for item in self):
            raise ValidationError(_("A cancelled club registration cannot accept players."))

    def action_collect_club_players(self):
        """Collect unregistered club players as drafts, never approve or bill them."""
        self.check_access("write")
        self._assert_open()
        License = self.env["federation.player.license"]
        for registration in self:
            players = self.env["federation.player"].search([
                ("club_id", "=", registration.club_id.id), ("active", "=", True),
            ])
            registered = License.search([
                ("season_id", "=", registration.season_id.id),
                ("player_id", "in", players.ids),
            ]).player_id
            registration._add_players(players - registered)
        return True

    def _add_players(self, players):
        self.ensure_one()
        self._registration_lock()
        self._assert_open()
        if any(player.club_id != self.club_id or not player.active for player in players):
            raise ValidationError(_("Select active players belonging to this club."))
        License = self.env["federation.player.license"]
        if License.search_count([
            ("player_id", "in", players.ids), ("season_id", "=", self.season_id.id),
        ]):
            raise ValidationError(_("One of these players already has a registration for this season."))
        try:
            with self.env.cr.savepoint():
                return self._create_player_licenses(players)
        except IntegrityError as error:
            raise ValidationError(_("A player was already registered for this season. Refresh the list.")) from error

    def _create_player_licenses(self, players):
        return self.env["federation.player.license"].create([
            {
                "player_id": player.id, "club_id": self.club_id.id,
                "season_id": self.season_id.id, "club_registration_id": self.id,
                "issue_date": self.season_id.date_start,
                "expiry_date": self.season_id.date_end,
                "state": "draft",
            }
            for player in players
        ])

    def action_submit(self):
        self._registration_lock()
        self._assert_open()
        if any(not item.pending_player_count for item in self):
            raise ValidationError(_("Add pending players before submitting."))
        self.write({"state": "submitted"})
        return True

    def action_confirm(self):
        self._registration_lock()
        self._assert_open()
        if any(not item.license_ids for item in self):
            raise ValidationError(_("A club registration must contain players."))
        # Previously approved players stay eligible during a top-up submission.
        self.mapped("license_ids").filtered(lambda item: item.state == "draft").action_activate()
        self.write({"state": "confirmed"})
        return True

    def action_cancel(self):
        self._registration_lock()
        self.mapped("license_ids").filtered(
            lambda item: item.state in ("draft", "active")
        ).action_cancel()
        self.write({"state": "cancelled"})
        return True

    def _registration_lock(self):
        self.check_access("write")
        if self:
            self.flush_recordset()
            self.env.cr.execute(
                "SELECT id FROM federation_club_season_registration WHERE id IN %s ORDER BY id FOR UPDATE",
                [tuple(self.ids)],
            )
            self.invalidate_recordset()
            self.check_access("write")
