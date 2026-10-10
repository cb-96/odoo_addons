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
        action = super().action_open_next_workspace()
        if action.get("type") == "ir.actions.act_window":
            model = self.env.get(action.get("res_model"))
            if model is not None and "edition_id" in model._fields:
                action["domain"] = [("edition_id", "=", self.id)]
                action["context"] = dict(
                    self.env.context,
                    default_edition_id=self.id,
                    search_default_edition_id=self.id,
                    competition_planner_edition_id=self.id,
                )
        return action
