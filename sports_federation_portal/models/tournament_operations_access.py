class TournamentOperationsAccessMixin:
    """Access-mode helpers for tournament operations actions."""

    def _operations_portal_write(
        self,
        match,
        write_values,
        portal_scope_domain,
        user,
    ):
        return self.env["federation.portal.privilege"].portal_write(
            match,
            write_values,
            scope_domain=portal_scope_domain,
            user=user,
        )

    def _operations_portal_call(
        self,
        match,
        method_name,
        portal_scope_domain,
        user,
    ):
        return self.env["federation.portal.privilege"].portal_call(
            match,
            method_name,
            scope_domain=portal_scope_domain,
            user=user,
        )

    def _operations_internal_write(self, match, write_values, user):
        return match.with_user(user).write(write_values)

    def _operations_internal_call(self, match, method_name, user):
        return getattr(match.with_user(user), method_name)()

    def _operations_get_action_handlers(
        self,
        match,
        access_mode,
        portal_scope_domain,
        user,
    ):
        if access_mode == "portal":
            return (
                lambda write_values: self._operations_portal_write(
                    match,
                    write_values,
                    portal_scope_domain,
                    user,
                ),
                lambda method_name: self._operations_portal_call(
                    match,
                    method_name,
                    portal_scope_domain,
                    user,
                ),
            )
        return (
            lambda write_values: self._operations_internal_write(
                match,
                write_values,
                user,
            ),
            lambda method_name: self._operations_internal_call(
                match,
                method_name,
                user,
            ),
        )
