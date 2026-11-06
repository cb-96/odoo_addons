from odoo import _, models


class MatchdayUsability(models.Model):
    _inherit = "federation.matchday"

    def action_open_focus_results(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.act_window", "name": _("Results for this match day"),
            "res_model": "federation.match", "view_mode": "list,form",
            "views": [(self.env.ref("sports_federation_setup_flow.result_focus_list").id, "list"), (False, "form")],
            "domain": [("id", "in", self.published_match_ids.filtered(lambda m: m.state == "done" and m.result_state != "approved").ids)],
        }

    def action_open_focus_history(self):
        self.ensure_one()
        self.check_access("read")
        return self.get_formview_action()


class MatchUsability(models.Model):
    _inherit = "federation.match"

    def action_open_quick_result(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.act_window", "name": _("Enter result"),
            "res_model": "federation.quick.result.wizard", "view_mode": "form", "target": "new",
            "context": {"default_match_id": self.id, "default_home_score": self.home_score, "default_away_score": self.away_score},
        }
