from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SeasonMembershipPolicy(models.Model):
    _inherit = "federation.season"

    player_membership_required = fields.Boolean(
        string="Require Federation Membership for Players", default=False,
        help="Optional prerequisite in addition to annual club player registration. "
             "Membership never replaces the player's season licence or creates its fee.",
    )


class PlayerRegistrationMembership(models.Model):
    _inherit = "federation.player.license"

    membership_status = fields.Selection(
        [("not_required", "Not required"), ("missing_identity", "Identity review needed"),
         ("missing", "Active player membership needed"), ("active", "Active membership")],
        compute="_compute_membership_status", string="Federation Membership",
        groups="sports_federation_base.group_federation_manager",
    )

    def _active_player_membership(self):
        self.ensure_one()
        person = self.player_id.sudo().person_id
        if not person:
            return self.env["federation.person.membership"]
        return self.env["federation.person.membership"].sudo().search([
            ("person_id", "=", person.id), ("club_id", "=", self.club_id.id),
            ("season_id", "=", self.season_id.id), ("role", "=", "player"),
            ("company_id", "=", self.club_registration_id.company_id.id),
            ("state", "=", "active"),
        ], limit=1)

    def _membership_blocker(self):
        self.ensure_one()
        if not self.season_id.player_membership_required:
            return False
        if not self.player_id.sudo().person_id:
            return _("Review and link this player's person identity before membership approval.")
        if not self._active_player_membership():
            return _("An active player membership for the same club, season and company is required.")
        return False

    @api.depends("player_id", "player_id.person_id", "season_id.player_membership_required", "club_id",
                 "player_id.person_id.registration_membership_ids.state",
                 "player_id.person_id.registration_membership_ids.role",
                 "player_id.person_id.registration_membership_ids.club_id",
                 "player_id.person_id.registration_membership_ids.season_id",
                 "player_id.person_id.registration_membership_ids.company_id")
    def _compute_membership_status(self):
        for license in self:
            if not license.season_id.player_membership_required:
                license.membership_status = "not_required"
            elif not license.player_id.sudo().person_id:
                license.membership_status = "missing_identity"
            else:
                license.membership_status = "active" if license._active_player_membership() else "missing"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered(lambda item: item.state == "active")._assert_membership()
        return records

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "active":
            self._assert_membership()
        return result

    def _assert_membership(self):
        for license in self:
            blocker = license._membership_blocker()
            if blocker:
                raise ValidationError(_("%(player)s: %(reason)s", player=license.player_id.display_name, reason=blocker))

    @api.model
    def _registered_players(self, club, season, reference_date):
        players = super()._registered_players(club, season, reference_date)
        if not season.player_membership_required:
            return players
        licenses = self.sudo().search([
            ("player_id", "in", players.ids), ("club_id", "=", club.id),
            ("season_id", "=", season.id), ("state", "=", "active"),
        ])
        return licenses.filtered(lambda item: not item._membership_blocker()).player_id

    def action_review_membership(self):
        self.ensure_one()
        self.check_access("read")
        # No automatic identity creation, membership activation or extra charge.
        person = self.player_id.person_id
        if not person:
            raise ValidationError(_("Use the reviewed identity workflow to link this player to a person first."))
        return {
            "type": "ir.actions.act_window", "name": _("Federation Membership"),
            "res_model": "federation.person.membership", "view_mode": "list,form",
            "domain": [("person_id", "=", person.id), ("club_id", "=", self.club_id.id),
                       ("season_id", "=", self.season_id.id), ("role", "=", "player"),
                       ("company_id", "=", self.club_registration_id.company_id.id)],
            "context": {"default_person_id": person.id, "default_club_id": self.club_id.id,
                        "default_season_id": self.season_id.id, "default_role": "player",
                        "default_company_id": self.club_registration_id.company_id.id},
        }


class RosterMembershipBoundary(models.Model):
    _inherit = "federation.team.roster.line"

    def _get_eligibility_reasons(self, reference_date=None):
        reasons = super()._get_eligibility_reasons(reference_date=reference_date)
        self.ensure_one()
        license = self.env["federation.player.license"].sudo().search([
            ("player_id", "=", self.player_id.id), ("club_id", "=", self.roster_id.club_id.id),
            ("season_id", "=", self.roster_id.season_id.id), ("state", "=", "active"),
        ], limit=1)
        if license:
            blocker = license._membership_blocker()
            if blocker:
                reasons.append(blocker)
        return reasons


class PersonMembershipDependency(models.Model):
    _inherit = "res.partner"

    registration_membership_ids = fields.One2many(
        "federation.person.membership", "person_id",
        groups="sports_federation_base.group_federation_manager",
    )


class RosterMembershipDependency(models.Model):
    _inherit = "federation.team.roster.line"

    @api.depends(
        "player_id.person_id.registration_membership_ids.state",
        "player_id.person_id.registration_membership_ids.club_id",
        "player_id.person_id.registration_membership_ids.season_id",
        "player_id.person_id.registration_membership_ids.role",
        "player_id.person_id.registration_membership_ids.company_id",
        "roster_id.season_id.player_membership_required",
    )
    def _compute_eligible(self):
        return super()._compute_eligible()


class MatchMembershipDependency(models.Model):
    _inherit = "federation.match.sheet.line"

    @api.depends(
        "player_id.person_id.registration_membership_ids.state",
        "player_id.person_id.registration_membership_ids.club_id",
        "player_id.person_id.registration_membership_ids.season_id",
        "player_id.person_id.registration_membership_ids.role",
        "player_id.person_id.registration_membership_ids.company_id",
        "match_sheet_id.match_id.tournament_id.season_id.player_membership_required",
    )
    def _compute_eligible(self):
        return super()._compute_eligible()


def _invalidate_registration_pickers(env):
    env["federation.player.license"].invalidate_model(["membership_status"])
    env["federation.team.roster"].invalidate_model(["season_registered_player_ids"])


class MembershipPickerRefresh(models.Model):
    _inherit = "federation.person.membership"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _invalidate_registration_pickers(self.env)
        return records

    def write(self, vals):
        result = super().write(vals)
        _invalidate_registration_pickers(self.env)
        return result

    def unlink(self):
        result = super().unlink()
        _invalidate_registration_pickers(self.env)
        return result


class SeasonPolicyPickerRefresh(models.Model):
    _inherit = "federation.season"

    def write(self, vals):
        result = super().write(vals)
        if "player_membership_required" in vals:
            _invalidate_registration_pickers(self.env)
        return result
