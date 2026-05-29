class CompetitionWorkspaceAccessMixin:
    """Access and dependent-service helpers for workspace service decomposition."""

    def _check_access(self, require_publish=False):
        return self.env["federation.tournament"]._competition_workspace_check_access(
            user=self.env.user,
            require_publish=require_publish,
        )

    def _validation_service(self):
        return self.env["federation.competition.workspace.validation.service"]

    def _read_model_service(self):
        return self.env["federation.competition.workspace.read.model.service"]
