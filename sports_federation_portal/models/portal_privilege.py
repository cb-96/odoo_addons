from odoo import _, api, models
from odoo.exceptions import AccessError


class FederationPortalPrivilege(models.AbstractModel):
    PORTAL_ACTION_ALLOWLIST = {
        "federation.competition.entry": {"action_submit", "action_withdraw"},
        "federation.document.submission": {"action_submit"},
        "federation.match": {"action_start", "action_done"},
        "federation.match.club.referee.duty": {"action_nominate"},
        "federation.match.referee": {"action_confirm", "action_cancel"},
        "federation.match.sheet": {
            "action_sync_gameday_roster",
            "action_set_crossed_out",
            "action_submit",
            "unlink",
        },
        # Deselecting a player in the game-day line-up removes the line.
        "federation.match.sheet.line": {"unlink"},
        "federation.season.registration": {"action_submit", "action_cancel"},
        "federation.team.roster": {
            "action_activate",
            "action_set_draft",
            "action_close",
            "action_reopen",
            "unlink",
        },
        "federation.team.roster.line": {"unlink"},
    }
    # Fields a portal command may change on an existing record. Deny by
    # default, like creation: a model or field that is not listed cannot be
    # written through ``portal_write``, whatever the caller passes. Keep each
    # set equal to what the owning portal method prepares.
    PORTAL_WRITE_FIELDS = {
        "federation.competition.entry": {"submission_note"},
        "federation.document.submission": {
            "issue_date",
            "expiry_date",
            "notes",
            # Resubmitting resets the review: back to draft, reviewer cleared.
            "status",
            "reviewer_id",
            "reviewed_on",
            "attachment_ids",
        },
        "federation.match.referee": {"response_note"},
        "federation.match.sheet": {
            "coach_id",
            "coach_name",
            "manager_id",
            "manager_name",
            "notes",
            "roster_id",
        },
        "federation.match.sheet.line": {
            "is_starter",
            "is_substitute",
            "is_captain",
            "jersey_number",
        },
        "federation.team.roster": {
            "season_registration_id",
            "name",
            "valid_from",
            "valid_to",
            "notes",
        },
        "federation.team.roster.line": {
            "roster_id",
            "player_id",
            "status",
            "jersey_number",
            "is_captain",
            "is_vice_captain",
            "license_id",
            "date_from",
            "date_to",
            "notes",
        },
    }
    PORTAL_CREATE_FIELDS = {
        "federation.competition.entry": {
            "window_id",
            "team_id",
            "submission_note",
            "submitted_by_id",
        },
        "federation.document.submission": {
            "requirement_id",
            # Target fields of the compliance requirement (club, official or
            # club representative; players for player requirements).
            "club_id",
            "player_id",
            "referee_id",
            "club_representative_id",
            "name",
            "notes",
            "status",
            "issue_date",
            "expiry_date",
        },
        # Must match the fields _portal_sync_squad sends for a newly selected
        # player; an unknown key turns the whole line-up save into an
        # AccessError (rendered as "Access Denied").
        "federation.match.sheet.line": {
            "match_sheet_id",
            "player_id",
            "roster_line_id",
            "is_captain",
            "jersey_number",
            "crossed_out",
        },
        "federation.player.parental.approval": {
            "player_id",
            "guardian_name",
            "guardian_email",
            "approval_date",
            "valid_until",
            "approval_document",
            "approval_document_filename",
            "state",
            "notes",
            "submitted_by_id",
            "submitted_on",
        },
        "federation.player": {
            "first_name",
            "last_name",
            "birth_date",
            "gender",
            "club_id",
            "public_visible",
            "email",
            "phone",
        },
        "federation.season.registration": {
            "season_id",
            "club_id",
            "team_id",
            "state",
            "notes",
            "user_id",
        },
        "federation.team": {
            "name",
            "club_id",
            "category",
            "gender",
            "email",
            "phone",
        },
        "federation.team.roster": {
            "team_id",
            "club_id",
            "season_id",
            "competition_id",
            "season_registration_id",
            "name",
            "valid_from",
            "valid_to",
        },
        "federation.team.roster.line": {
            "roster_id",
            "player_id",
            "license_id",
            "is_captain",
            "status",
            "jersey_number",
            "is_vice_captain",
            "date_from",
            "date_to",
            "notes",
        },
    }
    _name = "federation.portal.privilege"
    _description = "Federation Portal Privilege Boundary"

    @api.model
    def _log_portal_audit(
        self,
        event_type,
        description,
        records,
        user=None,
        action_name=False,
        changed_fields=False,
    ):
        """Capture one audit row per portal-managed target record."""
        # Every portal change can change the actor's tasks: their next page
        # view rebuilds the projection instead of reusing a recent one.
        self.env["federation.operation.task"]._forget_projection_for(
            user or self.env.user
        )
        audit_model = self.env.get("federation.audit.event")
        if audit_model is None:
            return False
        audit_model.log_record_events(
            event_family="portal_privilege",
            event_type=event_type,
            description=description,
            records=records,
            actor=user or self.env.user,
            action_name=action_name,
            changed_fields=changed_fields,
        )
        return True

    @api.model
    def elevate(self, records, user=None):
        """Return a recordset or model env elevated for a portal-owned action."""
        user = user or self.env.user
        return records.with_user(user).sudo()

    @api.model
    def portal_create(
        self, model_env, values, user=None, allowed_fields=None, scope_domain=None
    ):
        """Create through a deny-by-default model and field capability."""
        user = user or self.env.user
        policy = self.PORTAL_CREATE_FIELDS.get(model_env._name)
        if not policy:
            raise AccessError(_("Portal creation is not allowed for this model."))
        effective = policy & set(allowed_fields or policy)
        rejected = set(values) - effective
        if rejected:
            raise AccessError(
                _(
                    "Portal creation rejected unsupported fields: %(fields)s",
                    fields=", ".join(sorted(rejected)),
                )
            )
        created_records = self.elevate(model_env, user=user).create(values)
        if scope_domain:
            self._assert_portal_owns(created_records, scope_domain, user=user)
        self._log_portal_audit(
            event_type="portal_create",
            description=_("Created through the portal privilege boundary."),
            records=created_records,
            user=user,
            action_name="create",
            changed_fields=values.keys(),
        )
        return created_records

    @api.model
    def portal_write(self, records, values, scope_domain=None, user=None):
        """Write through the shared portal privilege boundary."""
        user = user or self.env.user
        policy = self.PORTAL_WRITE_FIELDS.get(records._name)
        if not policy:
            raise AccessError(_("Portal changes are not allowed for this model."))
        rejected = set(values) - policy
        if rejected:
            raise AccessError(
                _(
                    "Portal change rejected unsupported fields: %(fields)s",
                    fields=", ".join(sorted(rejected)),
                )
            )
        if not scope_domain:
            raise AccessError(
                _(
                    "Portal write operations must provide an explicit ownership scope domain."
                )
            )
        self._assert_portal_owns(records, scope_domain, user=user)
        privileged_records = self.elevate(records, user=user)
        result = privileged_records.write(values)
        if result:
            self._log_portal_audit(
                event_type="portal_write",
                description=_("Updated through the portal privilege boundary."),
                records=privileged_records,
                user=user,
                action_name="write",
                changed_fields=values.keys(),
            )
        return result

    @api.model
    def portal_call(
        self,
        records,
        method_name,
        *args,
        scope_domain=None,
        user=None,
        **kwargs,
    ):
        """Call a record method through the shared portal privilege boundary."""
        user = user or self.env.user
        if not scope_domain:
            raise AccessError(
                _(
                    "Portal call operations must provide an explicit ownership scope domain."
                )
            )
        allowed_actions = self.PORTAL_ACTION_ALLOWLIST.get(records._name, set())
        if method_name not in allowed_actions:
            raise AccessError(
                _("This action is not permitted through the portal privilege boundary.")
            )
        self._assert_portal_owns(records, scope_domain, user=user)
        privileged_records = self.elevate(records, user=user)
        method = getattr(privileged_records, method_name, None)
        if not callable(method):
            raise AccessError(_("The requested portal action is not available."))
        result = method(*args, **kwargs)
        self._log_portal_audit(
            event_type="portal_call",
            description=_("Executed a portal-managed record method."),
            records=privileged_records,
            user=user,
            action_name=method_name,
        )
        return result

    @api.model
    def _without_archived_competitions(self, model_env, domain):
        """Records of archived competitions are never part of a portal scope."""
        exclusion = self.env["federation.portal.archive.scope"].exclusion_domain(
            model_env._name
        )
        return list(domain or []) + exclusion

    @api.model
    def portal_search(self, model_env, domain, user=None, **kwargs):
        """Search through the shared portal privilege boundary."""
        domain = self._without_archived_competitions(model_env, domain)
        return self.elevate(model_env, user=user).search(domain, **kwargs)

    @api.model
    def portal_search_by_id(
        self, model_env, record_id, domain=None, user=None, **kwargs
    ):
        """Resolve one record id only when it matches the expected portal domain."""
        domain = list(domain or [])
        domain.append(("id", "=", record_id))
        return self.portal_search(model_env, domain, user=user, limit=1, **kwargs)

    @api.model
    def portal_search_count(self, model_env, domain, user=None, **kwargs):
        """Count records through the shared portal privilege boundary."""
        domain = self._without_archived_competitions(model_env, domain)
        return self.elevate(model_env, user=user).search_count(domain, **kwargs)

    @api.model
    def portal_assert_in_domain(self, records, domain, access_message, user=None):
        """Ensure all records are visible inside the expected portal domain."""
        records = records.exists()
        if not records:
            raise AccessError(access_message)

        privileged_records = self.elevate(records, user=user)
        allowed_count = privileged_records.search_count(
            self._without_archived_competitions(records, domain)
            + [("id", "in", records.ids)]
        )
        if allowed_count != len(records):
            raise AccessError(access_message)
        return privileged_records

    @api.model
    def _assert_portal_owns(self, records, scope_domain, user=None):
        """Assert the user's portal scope includes all supplied records.

        Convenience wrapper around :meth:`portal_assert_in_domain` that
        provides a consistent default access-denied message, so callers do not
        need to craft their own message text.  Use this as the canonical
        ownership assertion at every portal privilege boundary.
        """
        user = user or self.env.user
        return self.portal_assert_in_domain(
            records,
            scope_domain,
            _("You do not have access to this record."),
            user=user,
        )
