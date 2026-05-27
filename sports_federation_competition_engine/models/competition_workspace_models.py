from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

DIVISION_WORKSPACE_STATE_SELECTION = [
    ("draft", "Draft"),
    ("registration_open", "Registration Open"),
    ("registration_locked", "Registration Locked"),
    ("schedule_generated", "Schedule Generated"),
    ("planning", "Planning"),
    ("published", "Published"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("archived", "Archived"),
    ("cancelled", "Cancelled"),
]

PLANNING_FORMAT_SELECTION = [
    ("single_round_robin", "Single Round Robin"),
    ("double_round_robin", "Double Round Robin"),
    ("knockout", "Knockout"),
    ("pool_then_bracket", "Pool Then Bracket"),
    ("manual", "Manual"),
]

GAMEDAY_PLANNER_STATE_SELECTION = [
    ("draft", "Draft"),
    ("planned", "Planned"),
    ("validated", "Validated"),
    ("published", "Published"),
    ("locked", "Locked"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

DIVISION_WORKSPACE_ALLOWED_TRANSITIONS = {
    "draft": {"registration_open", "registration_locked", "cancelled"},
    "registration_open": {"registration_locked", "cancelled"},
    "registration_locked": {"planning", "schedule_generated", "cancelled"},
    "schedule_generated": {"planning", "published", "cancelled"},
    "planning": {"published", "schedule_generated", "cancelled"},
    "published": {"planning", "in_progress", "completed", "archived", "cancelled"},
    "in_progress": {"completed", "archived", "cancelled"},
    "completed": {"archived"},
    "archived": set(),
    "cancelled": set(),
}

GAMEDAY_PLANNER_ALLOWED_TRANSITIONS = {
    "draft": {"planned", "published", "cancelled"},
    "planned": {"validated", "published", "locked", "cancelled"},
    "validated": {"planned", "published", "locked", "cancelled"},
    "published": {"planned", "locked", "in_progress", "completed", "cancelled"},
    "locked": {"published", "in_progress", "completed", "cancelled"},
    "in_progress": {"completed", "locked", "cancelled"},
    "completed": {"locked"},
    "cancelled": set(),
}


class FederationCompetitionEdition(models.Model):
    _inherit = "federation.competition.edition"

    def action_open_competition_workspace(self):
        """Open the guided competition workspace client action."""
        self.ensure_one()
        self.env["federation.tournament"]._competition_workspace_check_access(
            user=self.env.user
        )
        return {
            "type": "ir.actions.client",
            "tag": "sports_federation_competition_engine.competition_workspace",
            "name": _("Competition Workspace"),
            "params": {
                "competition_id": self.id,
            },
        }


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    workspace_state = fields.Selection(
        DIVISION_WORKSPACE_STATE_SELECTION,
        string="Workspace State",
        default="draft",
        required=True,
        tracking=True,
        help="Guided planning workflow state used by the Competition Workspace.",
    )
    planning_format = fields.Selection(
        PLANNING_FORMAT_SELECTION,
        string="Planning Format",
        default="single_round_robin",
        required=True,
        tracking=True,
        help="Preferred competition format for the guided planning workflow.",
    )
    entries_locked = fields.Boolean(
        string="Entries Locked",
        default=False,
        tracking=True,
        help="Prevents planning from drifting after the participant list is confirmed.",
    )
    minimum_rest_minutes = fields.Integer(
        string="Minimum Rest (Minutes)",
        default=30,
        tracking=True,
        help="Soft warning threshold used when the planner schedules teams too close together.",
    )
    max_consecutive_matches_per_team = fields.Integer(
        string="Max Consecutive Matches Per Team",
        default=1,
        tracking=True,
        help="Maximum number of short-rest matches a team can play in a row on one gameday.",
    )
    pool_count = fields.Integer(
        string="Pool Count",
        default=2,
        tracking=True,
        help="Balanced pool count used when the planning format is Pool Then Bracket.",
    )
    pool_qualifier_count = fields.Integer(
        string="Qualifiers Per Pool",
        default=2,
        tracking=True,
        help="Number of teams that advance from each pool into the knockout stage.",
    )
    workspace_stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Workspace Stage",
        tracking=True,
        ondelete="set null",
        help="Default stage used by the Competition Workspace for round-robin planning.",
    )
    workspace_knockout_stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Workspace Knockout Stage",
        tracking=True,
        ondelete="set null",
        help="Knockout stage used by Pool Then Bracket and bracket planning flows.",
    )
    round_ids = fields.One2many(
        "federation.tournament.round",
        "tournament_id",
        string="Gamedays",
        readonly=True,
    )
    slot_ids = fields.One2many(
        "federation.match.slot",
        "tournament_id",
        string="Planner Slots",
        readonly=True,
    )

    @api.constrains("workspace_stage_id", "workspace_knockout_stage_id")
    def _check_workspace_stage_scope(self):
        """Keep the default planning stage inside the same division."""
        for record in self.filtered(
            lambda division: division.workspace_stage_id
            or division.workspace_knockout_stage_id
        ):
            if (
                record.workspace_stage_id
                and record.workspace_stage_id.tournament_id != record
            ):
                raise ValidationError(
                    _(
                        "The workspace stage must belong to the same division or tournament."
                    )
                )
            if (
                record.workspace_knockout_stage_id
                and record.workspace_knockout_stage_id.tournament_id != record
            ):
                raise ValidationError(
                    _(
                        "The workspace knockout stage must belong to the same division or tournament."
                    )
                )

    @api.constrains("planning_format", "pool_count", "pool_qualifier_count")
    def _check_pool_then_bracket_settings(self):
        """Validate Pool Then Bracket configuration."""
        for record in self.filtered(
            lambda division: division.planning_format == "pool_then_bracket"
        ):
            if record.pool_count < 2:
                raise ValidationError(
                    _("Pool Then Bracket requires at least two pools.")
                )
            if record.pool_qualifier_count < 1:
                raise ValidationError(
                    _(
                        "Pool Then Bracket requires at least one qualifier from each pool."
                    )
                )

    @api.constrains("minimum_rest_minutes", "max_consecutive_matches_per_team")
    def _check_planning_policy_values(self):
        for record in self:
            if (record.minimum_rest_minutes or 0) < 0:
                raise ValidationError(
                    _("Minimum rest must be zero or greater.")
                )
            if (record.max_consecutive_matches_per_team or 0) < 1:
                raise ValidationError(
                    _("Max consecutive matches per team must be at least one.")
                )

    @api.model
    def _competition_workspace_get_user_capabilities(self, user=None):
        """Return planning capabilities for the supplied internal user."""
        user = user or self.env.user
        is_manager = user.has_group("sports_federation_base.group_federation_manager")
        can_plan = is_manager or user.has_group(
            "sports_federation_competition_engine.group_federation_competition_planner"
        )
        return {
            "is_manager": is_manager,
            "can_plan": can_plan,
            "can_publish": is_manager,
            "can_force_assign": is_manager,
        }

    @api.model
    def _competition_workspace_check_access(self, user=None, require_publish=False):
        """Enforce Competition Workspace access server-side."""
        capabilities = self._competition_workspace_get_user_capabilities(user=user)
        if not capabilities["can_plan"]:
            raise AccessError(
                _(
                    "You do not have permission to access the Competition Workspace."
                )
            )
        if require_publish and not capabilities["can_publish"]:
            raise AccessError(
                _(
                    "Only federation managers can publish schedules from the Competition Workspace."
                )
            )
        return capabilities

    def _workspace_get_or_create_stage(self):
        """Return the planning stage used for guided scheduling."""
        self.ensure_one()
        desired_stage_type = (
            "knockout" if self.planning_format == "knockout" else "group"
        )
        if self.workspace_stage_id and self.workspace_stage_id.stage_type == desired_stage_type:
            return self.workspace_stage_id

        stage = self.stage_ids.filtered(
            lambda record: record.stage_type == desired_stage_type
        ).sorted(lambda record: (record.sequence, record.id))[:1]
        if stage:
            self.workspace_stage_id = stage.id
            return stage

        stage = self.env["federation.tournament.stage"].create(
            {
                "name": _("Knockout Bracket")
                if desired_stage_type == "knockout"
                else _("Pool Phase")
                if self.planning_format == "pool_then_bracket"
                else _("League Phase"),
                "tournament_id": self.id,
                "sequence": 10,
                "stage_type": desired_stage_type,
            }
        )
        self.workspace_stage_id = stage.id
        return stage

    def _workspace_get_or_create_knockout_stage(self):
        """Return the knockout stage used by bracket-oriented planning formats."""
        self.ensure_one()
        if self.planning_format == "knockout":
            return self._workspace_get_or_create_stage()
        if self.planning_format != "pool_then_bracket":
            return False

        if (
            self.workspace_knockout_stage_id
            and self.workspace_knockout_stage_id.stage_type == "knockout"
        ):
            return self.workspace_knockout_stage_id

        stage = self.stage_ids.filtered(
            lambda record: record.stage_type == "knockout"
        ).sorted(lambda record: (record.sequence, record.id))[:1]
        if stage:
            self.workspace_knockout_stage_id = stage.id
            return stage

        stage = self.env["federation.tournament.stage"].create(
            {
                "name": _("Knockout Bracket"),
                "tournament_id": self.id,
                "sequence": max(self.stage_ids.mapped("sequence") or [10]) + 10,
                "stage_type": "knockout",
            }
        )
        self.workspace_knockout_stage_id = stage.id
        return stage

    def action_open_competition_workspace(self):
        """Open the guided workspace anchored on this division."""
        self.ensure_one()
        self._competition_workspace_check_access(user=self.env.user)
        return {
            "type": "ir.actions.client",
            "tag": "sports_federation_competition_engine.competition_workspace",
            "name": _("Competition Workspace"),
            "params": {
                "competition_id": self.edition_id.id if self.edition_id else False,
                "division_id": self.id,
            },
        }

    def action_lock_team_entries(self):
        """Lock the participant list for guided schedule generation."""
        self._competition_workspace_check_access(user=self.env.user)
        for record in self:
            confirmed_participants = record.participant_ids.filtered(
                lambda participant: participant.state == "confirmed"
            )
            if len(confirmed_participants) < 2:
                raise ValidationError(
                    _(
                        "Confirm at least two team entries before locking the participant list."
                    )
                )
            record.write({"entries_locked": True})
            record._competition_workspace_transition_state("registration_locked")
        return True

    def _competition_workspace_state_label(self, field_name, value):
        self.ensure_one()
        field = self._fields.get(field_name)
        if not field or not field.selection:
            return value
        return dict(field.selection).get(value, value)

    def _competition_workspace_log_transition(
        self, field_name, old_value, new_value, reason=False, actor=False
    ):
        self.ensure_one()
        if not reason or not hasattr(self, "message_post"):
            return
        actor = actor or self.env.user
        self.message_post(
            body=_(
                "Competition Workspace moved %(field)s from %(old)s to %(new)s by %(actor)s. Reason: %(reason)s",
                field=self._fields[field_name].string or field_name,
                old=self._competition_workspace_state_label(field_name, old_value),
                new=self._competition_workspace_state_label(field_name, new_value),
                actor=actor.display_name,
                reason=reason,
            )
        )

    def _competition_workspace_transition_state(
        self, target_state, reason=False, actor=False
    ):
        for record in self:
            current_state = record.workspace_state or "draft"
            if current_state == target_state:
                continue
            allowed_transitions = DIVISION_WORKSPACE_ALLOWED_TRANSITIONS.get(
                current_state, set()
            )
            if target_state not in allowed_transitions:
                raise ValidationError(
                    _(
                        "Cannot move %(division)s from %(current)s to %(target)s in the Competition Workspace.",
                        division=record.display_name,
                        current=record._competition_workspace_state_label(
                            "workspace_state", current_state
                        ),
                        target=record._competition_workspace_state_label(
                            "workspace_state", target_state
                        ),
                    )
                )
            record.write({"workspace_state": target_state})
            record._competition_workspace_log_transition(
                "workspace_state",
                current_state,
                target_state,
                reason=reason,
                actor=actor,
            )
        return True


class FederationTournamentRound(models.Model):
    _inherit = "federation.tournament.round"

    planner_state = fields.Selection(
        GAMEDAY_PLANNER_STATE_SELECTION,
        string="Planner State",
        default="draft",
        required=True,
        help="Operational state used by the Competition Workspace planner.",
    )
    slot_ids = fields.One2many(
        "federation.match.slot",
        "round_id",
        string="Planner Slots",
    )
    slot_count = fields.Integer(
        string="Slot Count",
        compute="_compute_slot_count",
        store=False,
    )
    planner_root_round_id = fields.Many2one(
        "federation.tournament.round",
        string="Planner Root Gameday",
        copy=False,
        index=True,
        ondelete="cascade",
        help="Links guest-division gamedays to the slot-owning shared planner round.",
    )
    planner_linked_round_ids = fields.One2many(
        "federation.tournament.round",
        "planner_root_round_id",
        string="Linked Planner Gamedays",
        readonly=True,
    )
    publish_locked = fields.Boolean(
        string="Publish Locked",
        default=False,
        help="Prevents non-manager schedule changes once a gameday is published.",
    )
    planner_revision = fields.Integer(
        string="Planner Revision",
        default=0,
        copy=False,
        help="Incremented whenever planner assignments, slot grids, or publication state change so stale planner writes can be rejected.",
    )
    schedule_live_revision_id = fields.Many2one(
        "federation.competition.schedule.revision",
        string="Live Schedule Revision",
        copy=False,
        ondelete="set null",
        help="Most recently published live schedule snapshot for this planner root gameday.",
    )
    schedule_draft_revision_id = fields.Many2one(
        "federation.competition.schedule.revision",
        string="Draft Schedule Revision",
        copy=False,
        ondelete="set null",
        help="Current draft schedule snapshot that can diverge from the published live revision.",
    )

    def _compute_slot_count(self):
        for record in self:
            record.slot_count = len(record.slot_ids)

    def _competition_workspace_root_round(self):
        self.ensure_one()
        return self.planner_root_round_id or self

    def _competition_workspace_linked_rounds(self):
        self.ensure_one()
        root_round = self._competition_workspace_root_round()
        return root_round | root_round.planner_linked_round_ids

    def _competition_workspace_state_label(self, field_name, value):
        self.ensure_one()
        field = self._fields.get(field_name)
        if not field or not field.selection:
            return value
        return dict(field.selection).get(value, value)

    def _competition_workspace_log_transition(
        self, field_name, old_value, new_value, reason=False, actor=False
    ):
        self.ensure_one()
        if not reason or not hasattr(self, "message_post"):
            return
        actor = actor or self.env.user
        self.message_post(
            body=_(
                "Competition Workspace moved %(field)s from %(old)s to %(new)s by %(actor)s. Reason: %(reason)s",
                field=self._fields[field_name].string or field_name,
                old=self._competition_workspace_state_label(field_name, old_value),
                new=self._competition_workspace_state_label(field_name, new_value),
                actor=actor.display_name,
                reason=reason,
            )
        )

    def _competition_workspace_transition_planner_state(
        self, target_state, reason=False, actor=False
    ):
        for record in self:
            current_state = record.planner_state or "draft"
            if current_state == target_state:
                continue
            allowed_transitions = GAMEDAY_PLANNER_ALLOWED_TRANSITIONS.get(
                current_state, set()
            )
            if target_state not in allowed_transitions:
                raise ValidationError(
                    _(
                        "Cannot move %(gameday)s from %(current)s to %(target)s in the Competition Workspace.",
                        gameday=record.display_name,
                        current=record._competition_workspace_state_label(
                            "planner_state", current_state
                        ),
                        target=record._competition_workspace_state_label(
                            "planner_state", target_state
                        ),
                    )
                )
            record.write({"planner_state": target_state})
            record._competition_workspace_log_transition(
                "planner_state",
                current_state,
                target_state,
                reason=reason,
                actor=actor,
            )
        return True

    def _competition_workspace_check_revision(self, expected_revision=False):
        for record in self:
            if expected_revision is False or expected_revision is None or expected_revision == "":
                continue
            root_round = record._competition_workspace_root_round()
            try:
                normalized_revision = int(expected_revision)
            except (TypeError, ValueError):
                raise ValidationError(_("The planner revision token is invalid."))
            if root_round.planner_revision != normalized_revision:
                raise ValidationError(
                    _(
                        "This planner changed in another session. Refresh the Competition Workspace and try again."
                    )
                )
        return True

    def _competition_workspace_bump_revision(self):
        root_rounds = self.env["federation.tournament.round"]
        seen_root_ids = set()
        for record in self:
            root_round = record._competition_workspace_root_round()
            if root_round.id in seen_root_ids:
                continue
            seen_root_ids.add(root_round.id)
            root_rounds |= root_round
        for root_round in root_rounds:
            root_round.write({"planner_revision": root_round.planner_revision + 1})
        return True

    @api.constrains("planner_root_round_id", "stage_id", "round_date")
    def _check_planner_root_round_scope(self):
        for record in self.filtered("planner_root_round_id"):
            root_round = record.planner_root_round_id
            if root_round == record:
                raise ValidationError(
                    _("A shared planner gameday cannot point to itself as its root round.")
                )
            if root_round.planner_root_round_id:
                raise ValidationError(
                    _("Shared planner gamedays can only link to a slot-owning root round.")
                )
            if record.tournament_id == root_round.tournament_id:
                raise ValidationError(
                    _("Use the root gameday directly for its own division.")
                )
            if record.tournament_id.edition_id != root_round.tournament_id.edition_id:
                raise ValidationError(
                    _("Shared planner gamedays must belong to divisions from the same competition.")
                )
            if record.round_date and root_round.round_date and record.round_date != root_round.round_date:
                raise ValidationError(
                    _("Shared planner gamedays must use the same calendar date across divisions.")
                )

    def action_open_competition_planner(self):
        """Open the workspace directly on this gameday planner."""
        self.ensure_one()
        self.tournament_id._competition_workspace_check_access(user=self.env.user)
        return {
            "type": "ir.actions.client",
            "tag": "sports_federation_competition_engine.competition_workspace",
            "name": _("Competition Planner"),
            "params": {
                "competition_id": self.tournament_id.edition_id.id
                if self.tournament_id.edition_id
                else False,
                "division_id": self.tournament_id.id,
                "gameday_id": self.id,
            },
        }


class FederationMatch(models.Model):
    _inherit = "federation.match"

    slot_id = fields.Many2one(
        "federation.match.slot",
        string="Planner Slot",
        ondelete="set null",
        copy=False,
        tracking=True,
    )

    @api.constrains("slot_id", "round_id")
    def _check_slot_round_scope(self):
        """Keep planner slot linkage consistent with the selected gameday."""
        for record in self.filtered("slot_id"):
            if (
                record.round_id
                and record.slot_id.round_id._competition_workspace_root_round()
                != record.round_id._competition_workspace_root_round()
            ):
                raise ValidationError(
                    _(
                        "The selected planner slot must belong to the same shared gameday as the match."
                    )
                )