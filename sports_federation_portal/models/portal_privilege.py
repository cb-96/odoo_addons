from odoo import _, api, models
from odoo.exceptions import AccessError


class FederationPortalPrivilege(models.AbstractModel):
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
    def portal_create(self, model_env, values, user=None):
        """Create a record through the shared portal privilege boundary."""
        created_records = self.elevate(model_env, user=user).create(values)
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
    def portal_write(self, records, values, user=None):
        """Write through the shared portal privilege boundary."""
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
    def portal_call(self, records, method_name, *args, user=None, **kwargs):
        """Call a record method through the shared portal privilege boundary."""
        privileged_records = self.elevate(records, user=user)
        result = getattr(privileged_records, method_name)(*args, **kwargs)
        self._log_portal_audit(
            event_type="portal_call",
            description=_("Executed a portal-managed record method."),
            records=privileged_records,
            user=user,
            action_name=method_name,
        )
        return result

    @api.model
    def portal_search(self, model_env, domain, user=None, **kwargs):
        """Search through the shared portal privilege boundary."""
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
        return self.elevate(model_env, user=user).search_count(domain, **kwargs)

    @api.model
    def portal_assert_in_domain(self, records, domain, access_message, user=None):
        """Ensure all records are visible inside the expected portal domain."""
        records = records.exists()
        if not records:
            raise AccessError(access_message)

        privileged_records = self.elevate(records, user=user)
        allowed_count = privileged_records.search_count(
            list(domain) + [("id", "in", records.ids)]
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
        return self.portal_assert_in_domain(
            records,
            scope_domain,
            _("You do not have access to this record."),
            user=user,
        )
