from odoo import _, models


class FederationCompetitionEditionSetupCompatibility(models.Model):
    _inherit = "federation.competition.edition"

    def action_open_next_workspace(self):
        """Compatibility entry point for bookmarks and downstream modules.

        The operator journey has one canonical router. The former workspace router
        remains callable so existing XML IDs, buttons, and integrations do not
        break during the consolidation window.
        """
        return self.action_continue_setup()

    def action_open_advanced_workspace(self):
        """Keep the former technical router available to federation managers."""
        self.ensure_one()
        return super().action_open_next_workspace()
