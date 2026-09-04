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
        [
            ("referee", "Federation Referee"),
            ("club", "One Club Duty"),
            ("auto_club", "Auto-assign Club Duties"),
        ],
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
    officials_per_match = fields.Integer(
        default=4,
        required=True,
        help="Number of club-supplied officials requested for each match.",
    )
    avoid_clubs_playing_same_slot = fields.Boolean(
        default=True,
        help="Prefer a club that has no team playing during the match slot.",
    )
    allow_playing_club_fallback = fields.Boolean(
        default=True,
        help="Allow the least-conflicted club when every eligible club is playing.",
    )
    preserve_existing_assignments = fields.Boolean(
        default=True,
        help="Keep existing federation/volunteer referee assignments and club duties.",
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

    @api.depends(
        "matchday_id",
        "assignment_type",
        "role",
        "referee_id",
        "club_id",
        "officials_per_match",
        "preserve_existing_assignments",
    )
    def _compute_preview(self):
        for wizard in self:
            if not wizard.matchday_id or not wizard.role:
                wizard.matches_total = wizard.matches_to_assign = 0
                wizard.matches_skipped = 0
                continue
            matches = wizard._published_matches()
            if wizard.assignment_type == "auto_club":
                roles = wizard._auto_roles()
                covered = wizard._covered_match_ids(matches, roles)
                wizard.matches_total = len(matches)
                wizard.matches_skipped = len(covered)
                wizard.matches_to_assign = len(matches) - len(covered)
                continue
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


    def _auto_roles(self):
        self.ensure_one()
        if not 1 <= self.officials_per_match <= len(ROLE_SELECTION):
            raise ValidationError(
                _("Officials per match must be between 1 and %s.")
                % len(ROLE_SELECTION)
            )
        return [role for role, _label in ROLE_SELECTION[: self.officials_per_match]]

    def _existing_roles(self, matches):
        referee_roles = self.env["federation.match.referee"].search(
            [
                ("match_id", "in", matches.ids),
                ("state", "!=", "cancelled"),
            ]
        )
        duty_roles = self.env["federation.match.club.referee.duty"].search(
            [("match_id", "in", matches.ids), ("state", "!=", "rejected")]
        )
        result = {}
        for assignment in referee_roles:
            result.setdefault(assignment.match_id.id, set()).add(assignment.role)
        for duty in duty_roles:
            result.setdefault(duty.match_id.id, set()).add(duty.role)
        return result

    def _covered_match_ids(self, matches, roles):
        if not self.preserve_existing_assignments:
            return set()
        existing = self._existing_roles(matches)
        return {
            match.id
            for match in matches
            if all(role in existing.get(match.id, set()) for role in roles)
        }

    @staticmethod
    def _match_club_ids(match):
        fixture = match.logical_fixture_id
        return {
            club.id
            for club in (fixture.home_team_id.club_id, fixture.away_team_id.club_id)
            if club
        }

    def _auto_assign_club_duties(self, matches):
        roles = self._auto_roles()
        existing_roles = self._existing_roles(matches)
        candidate_clubs = matches.mapped("logical_fixture_id.home_team_id.club_id")
        candidate_clubs |= matches.mapped("logical_fixture_id.away_team_id.club_id")
        if not candidate_clubs:
            raise ValidationError(_("No participating clubs are available for duties."))
        load = {club.id: 0 for club in candidate_clubs}
        existing_duties = self.env["federation.match.club.referee.duty"].search(
            [("match_id", "in", matches.ids), ("state", "!=", "rejected")]
        )
        for duty in existing_duties:
            load[duty.club_id.id] = load.get(duty.club_id.id, 0) + 1
        values = []
        for match in matches.sorted(lambda item: (item.date_scheduled, item.id)):
            missing_roles = [
                role
                for role in roles
                if not (
                    self.preserve_existing_assignments
                    and role in existing_roles.get(match.id, set())
                )
            ]
            if not missing_roles:
                continue
            slot = match.published_slot_id or match.operational_slot_id
            simultaneous = matches.filtered(
                lambda other: other.id != match.id
                and (other.published_slot_id or other.operational_slot_id) == slot
            )
            playing_clubs = set().union(
                *(self._match_club_ids(other) for other in simultaneous | match)
            )
            opponents = self._match_club_ids(match)
            eligible = candidate_clubs.filtered(lambda club: club.id not in opponents)
            preferred = eligible.filtered(lambda club: club.id not in playing_clubs)
            pool = (
                preferred
                if self.avoid_clubs_playing_same_slot and preferred
                else eligible
            )
            if (
                self.avoid_clubs_playing_same_slot
                and not preferred
                and not self.allow_playing_club_fallback
            ):
                raise ValidationError(
                    _("No non-playing club is available for %s.") % match.display_name
                )
            if not pool:
                raise ValidationError(
                    _("No other participating club can cover %s.") % match.display_name
                )
            club = min(
                pool,
                key=lambda candidate: (
                    candidate.id in playing_clubs,
                    load.get(candidate.id, 0),
                    candidate.id,
                ),
            )
            for role in missing_roles:
                values.append(
                    {
                        "match_id": match.id,
                        "club_id": club.id,
                        "role": role,
                    }
                )
                load[club.id] = load.get(club.id, 0) + 1
        duties = self.env["federation.match.club.referee.duty"].create(values)
        if self.open_duties:
            duties.action_open()
        return duties

    def action_apply(self):
        self.ensure_one()
        matches = self._published_matches()
        if not matches:
            raise ValidationError(
                _("The live publication contains no assignable matches.")
            )
        if self.assignment_type == "auto_club":
            self._auto_assign_club_duties(matches)
            return {"type": "ir.actions.act_window_close"}
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
