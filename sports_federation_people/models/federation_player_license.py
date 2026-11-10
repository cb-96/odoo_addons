from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationPlayerLicense(models.Model):
    _name = "federation.player.license"
    _description = "Player License"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "issue_date desc, id"

    name = fields.Char(string="License Number", required=True, copy=False, default="New")
    club_registration_id = fields.Many2one(
        "federation.club.season.registration", string="Club Season Registration",
        ondelete="restrict", index=True,
    )
    player_id = fields.Many2one(
        "federation.player", string="Player", required=True, ondelete="cascade"
    )
    season_id = fields.Many2one(
        "federation.season", string="Season", required=True, ondelete="restrict"
    )
    club_id = fields.Many2one(
        "federation.club", string="Club", required=True, ondelete="restrict"
    )
    issue_date = fields.Date(
        string="Issue Date", required=True, default=fields.Date.context_today
    )
    expiry_date = fields.Date(string="Expiry Date", required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
    )
    category = fields.Selection(
        [
            ("senior", "Senior"),
            ("youth", "Youth"),
            ("junior", "Junior"),
            ("cadet", "Cadet"),
        ],
        string="Category",
    )
    eligibility_notes = fields.Text(string="Eligibility Notes")
    notes = fields.Text(string="Notes")

    _player_season_unique = models.Constraint(
        "unique (player_id, season_id)",
        "A player can only have one license per season.",
    )

    @api.constrains("issue_date", "expiry_date")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.issue_date and rec.expiry_date and rec.expiry_date <= rec.issue_date:
                raise ValidationError("Expiry date must be after issue date.")

    def action_activate(self):
        """Execute the activate action."""
        for rec in self:
            rec.state = "active"

    def action_cancel(self):
        """Execute the cancel action."""
        for rec in self:
            rec.state = "cancelled"

    def action_draft(self):
        """Execute the draft action."""
        for rec in self:
            rec.state = "draft"

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        Registration = self.env["federation.club.season.registration"]
        defaults = self.default_get(["club_id", "season_id"])
        for vals in vals_list:
            registration = Registration.browse(vals.get("club_registration_id"))
            for field in ("club_id", "season_id"):
                if not vals.get(field):
                    vals[field] = registration[field].id if registration else defaults.get(field)
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "federation.player.license"
                ) or "New"
            if not vals.get("club_registration_id") and vals.get("club_id") and vals.get("season_id"):
                vals["club_registration_id"] = Registration._get_or_create(
                    self.env["federation.club"].browse(vals["club_id"]),
                    self.env["federation.season"].browse(vals["season_id"]),
                ).id
        Registration.browse(sorted({vals["club_registration_id"] for vals in vals_list}))._registration_lock()
        for vals in vals_list:
            if vals.get("state", "draft") in ("draft", "active"):
                player = self.env["federation.player"].browse(vals.get("player_id"))
                if not player.active or player.club_id.id != vals.get("club_id"):
                    raise ValidationError(_("Register an active player with their current club."))
        return super().create(vals_list)

    def write(self, vals):
        self.check_access("write")
        self.mapped("club_registration_id")._registration_lock()
        self.invalidate_recordset()
        if vals.get("state") == "active":
            for license in self:
                if license.state == "cancelled":
                    raise ValidationError(_("Cancelled player registrations cannot be reactivated implicitly."))
                if license.state != "active" and (
                    not license.player_id.active or license.player_id.club_id != license.club_id
                ):
                    raise ValidationError(_("Approve an active player with their current club."))
        if vals.get("state") == "draft" and any(license.state != "draft" for license in self):
            raise ValidationError(_("Approved registration history cannot be reset to draft."))
        scope = {"player_id", "club_id", "season_id", "club_registration_id"}
        if scope.intersection(vals):
            for license in self:
                changed = any(
                    key in vals and vals[key] != license[key].id for key in scope
                )
                if changed and license.state != "draft":
                    raise ValidationError(_("An approved licence cannot change player, club or season."))
        return super().write(vals)

    def unlink(self):
        if any(license.state != "draft" for license in self):
            raise ValidationError(_("Keep approved player registration history; cancel it instead."))
        return super().unlink()

    @api.constrains("club_registration_id", "club_id", "season_id", "player_id", "state")
    def _check_club_registration(self):
        for license in self:
            registration = license.club_registration_id
            if not registration or registration.club_id != license.club_id or registration.season_id != license.season_id:
                raise ValidationError(_("The player licence must match its club season registration."))
            if license.state in ("draft", "active") and registration.state == "cancelled":
                raise ValidationError(_("A cancelled club registration cannot contain pending or active players."))
            if license.state == "draft" and license.player_id.club_id != license.club_id:
                raise ValidationError(_("Register the player with their current club."))

    @api.model
    def _registered_players(self, club, season, reference_date):
        """Mandatory annual scope, independent of optional sport eligibility rules."""
        return self.search([
            ("club_id", "=", club.id), ("season_id", "=", season.id),
            ("state", "=", "active"), ("issue_date", "<=", reference_date),
            ("expiry_date", ">=", reference_date),
        ]).player_id
