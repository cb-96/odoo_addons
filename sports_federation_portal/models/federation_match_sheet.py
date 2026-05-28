from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationMatchSheet(models.Model):
    _inherit = "federation.match.sheet"

    # ── Club-linked coach / manager ───────────────────────────────────────
    # These Many2one fields give backend users a filtered picker instead of
    # a free-text name box.  Selecting a representative auto-fills the
    # legacy coach_name / manager_name Char fields so the portal and match
    # sheet read-only views continue to work unchanged.

    # Relay field so the view domain on coach_id / manager_id can reference
    # the team's club without dot-notation (unsupported in Odoo view domains).
    team_club_id = fields.Many2one(
        "federation.club",
        compute="_compute_team_club_id",
        string="Team Club",
        store=False,
    )
    coach_id = fields.Many2one(
        "federation.club.representative",
        string="Coach",
        ondelete="set null",
        help="Coach listed on the match sheet. Filtered to coach-role representatives of the team's club.",
    )
    manager_id = fields.Many2one(
        "federation.club.representative",
        string="Manager",
        ondelete="set null",
        help="Manager listed on the match sheet. Filtered to representatives of the team's club.",
    )

    @api.depends("team_id")
    def _compute_team_club_id(self):
        for rec in self:
            rec.team_club_id = rec.team_id.club_id

    @api.onchange("coach_id")
    def _onchange_coach_id(self):
        """Populate coach_name from the selected representative's partner name."""
        if self.coach_id:
            self.coach_name = self.coach_id.partner_id.name

    @api.onchange("manager_id")
    def _onchange_manager_id(self):
        """Populate manager_name from the selected representative's partner name."""
        if self.manager_id:
            self.manager_name = self.manager_id.partner_id.name

    @api.onchange("team_id")
    def _onchange_team_id_portal_coach(self):
        """Clear coach/manager pickers when team changes to avoid stale references."""
        self.coach_id = False
        self.manager_id = False

    @api.model
    def _portal_get_domain(self, user=None):
        """Handle the portal-specific get domain flow."""
        user = user or self.env.user
        club_scope = user.portal_club_scope_ids
        team_scope = user.portal_team_scope_ids
        if team_scope and club_scope:
            return [
                "|",
                ("team_id", "in", team_scope.ids),
                ("team_id.club_id", "in", club_scope.ids),
            ]
        if team_scope:
            return [("team_id", "in", team_scope.ids)]
        if club_scope:
            return [("team_id.club_id", "in", club_scope.ids)]
        return [("id", "=", False)]

    def _portal_assert_review_access(self, user=None):
        """Handle the portal-specific assert review access flow."""
        user = user or self.env.user
        domain = self._portal_get_domain(user=user)
        if domain == [("id", "=", False)]:
            raise AccessError(_("You do not have portal access to match sheets."))
        self.env["federation.portal.privilege"].portal_assert_in_domain(
            self,
            domain,
            _("You can only review match sheets for your assigned teams or club."),
            user=user,
        )
        return True

    def _portal_update_preparation(self, values=None, user=None):
        """Handle the portal-specific update preparation flow."""
        user = user or self.env.user
        self._portal_assert_review_access(user=user)
        locked = self.filtered(lambda sheet: sheet.state == "locked")
        if locked:
            raise ValidationError(
                _("Locked match sheets cannot be updated from the portal.")
            )
        values = values or {}
        prepared = {}

        # coach_id takes priority; auto-fills coach_name from the representative
        if "coach_id" in values:
            raw = values.get("coach_id")
            if raw:
                try:
                    coach = (
                        self.env["federation.club.representative"]
                        .sudo()
                        .browse(int(raw))
                    )
                except (ValueError, TypeError):
                    coach = self.env["federation.club.representative"].browse()
                if coach.exists():
                    for rec in self:
                        if coach.club_id == rec.team_id.club_id:
                            prepared["coach_id"] = coach.id
                            prepared["coach_name"] = coach.partner_id.name
            else:
                prepared["coach_id"] = False
                if "coach_name" in values:
                    prepared["coach_name"] = (
                        values.get("coach_name") or ""
                    ).strip() or False
        elif "coach_name" in values:
            prepared["coach_name"] = (values.get("coach_name") or "").strip() or False

        # manager_id takes priority; auto-fills manager_name
        if "manager_id" in values:
            raw = values.get("manager_id")
            if raw:
                try:
                    manager = (
                        self.env["federation.club.representative"]
                        .sudo()
                        .browse(int(raw))
                    )
                except (ValueError, TypeError):
                    manager = self.env["federation.club.representative"].browse()
                if manager.exists():
                    for rec in self:
                        if manager.club_id == rec.team_id.club_id:
                            prepared["manager_id"] = manager.id
                            prepared["manager_name"] = manager.partner_id.name
            else:
                prepared["manager_id"] = False
                if "manager_name" in values:
                    prepared["manager_name"] = (
                        values.get("manager_name") or ""
                    ).strip() or False
        elif "manager_name" in values:
            prepared["manager_name"] = (
                values.get("manager_name") or ""
            ).strip() or False

        if "notes" in values:
            prepared["notes"] = (values.get("notes") or "").strip() or False

        # roster_id: validate the roster belongs to the sheet's team
        if "roster_id" in values:
            raw = values.get("roster_id")
            if raw:
                try:
                    roster = self.env["federation.team.roster"].sudo().browse(int(raw))
                except (ValueError, TypeError):
                    roster = self.env["federation.team.roster"].browse()
                if roster.exists():
                    for rec in self:
                        if roster.team_id == rec.team_id:
                            prepared["roster_id"] = roster.id
                            break
            else:
                prepared["roster_id"] = False

        if prepared:
            scope_domain = self._portal_get_domain(user=user)
            self.env["federation.portal.privilege"].portal_write(
                self,
                prepared,
                scope_domain=scope_domain,
                user=user,
            )
        return True

    def _portal_sync_squad(self, squad_data, user=None):
        """Sync match sheet lines from a portal squad selection.

        squad_data is a list of dicts:
            [{"player_id": int, "role": "starter"|"substitute"|"other",
              "is_captain": bool, "jersey_number": str|False}]
        Only players that exist on the linked roster are accepted.
        """
        user = user or self.env.user
        self._portal_assert_review_access(user=user)
        Privilege = self.env["federation.portal.privilege"]

        for sheet in self:
            if sheet.state != "draft":
                raise ValidationError(
                    _("Squad selection can only be changed on draft match sheets.")
                )
            if not sheet.roster_id:
                raise ValidationError(
                    _("A roster must be linked before managing the squad.")
                )

            valid_player_ids = set(sheet.roster_id.line_ids.mapped("player_id").ids)
            submitted = {
                d["player_id"]: d
                for d in squad_data
                if d["player_id"] in valid_player_ids
            }
            existing_lines = {line.player_id.id: line for line in sheet.line_ids}

            # Remove lines whose players were unchecked
            to_remove = sheet.line_ids.filtered(
                lambda ln: ln.player_id.id not in submitted
            )
            if to_remove:
                Privilege.portal_call(
                    to_remove,
                    "unlink",
                    scope_domain=[("match_sheet_id", "=", sheet.id)],
                    user=user,
                )

            # Add or update selected players
            for player_id, data in submitted.items():
                is_starter = data.get("role") == "starter"
                is_substitute = data.get("role") == "substitute"
                is_captain = bool(data.get("is_captain"))
                jersey_number = data.get("jersey_number") or False
                roster_line = sheet.roster_id.line_ids.filtered(
                    lambda ln, pid=player_id: ln.player_id.id == pid
                )[:1]

                if player_id in existing_lines:
                    Privilege.portal_write(
                        existing_lines[player_id],
                        {
                            "is_starter": is_starter,
                            "is_substitute": is_substitute,
                            "is_captain": is_captain,
                            "jersey_number": jersey_number,
                        },
                        scope_domain=[("match_sheet_id", "=", sheet.id)],
                        user=user,
                    )
                else:
                    Privilege.portal_create(
                        self.env["federation.match.sheet.line"],
                        {
                            "match_sheet_id": sheet.id,
                            "player_id": player_id,
                            "roster_line_id": roster_line.id if roster_line else False,
                            "is_starter": is_starter,
                            "is_substitute": is_substitute,
                            "is_captain": is_captain,
                            "jersey_number": jersey_number,
                        },
                        user=user,
                    )
        return True

    def _portal_action_submit(self, user=None):
        """Handle the portal-specific action submit flow."""
        user = user or self.env.user
        self._portal_assert_review_access(user=user)
        drafts = self.filtered(lambda sheet: sheet.state == "draft")
        if not drafts:
            raise ValidationError(
                _("Only draft match sheets can be submitted from the portal.")
            )
        return self.env["federation.portal.privilege"].portal_call(
            drafts,
            "action_submit",
            scope_domain=self._portal_get_domain(user=user),
            user=user,
        )
