from odoo import api, models


class FederationQolSearch(models.AbstractModel):
    _name = "federation.qol.search"
    _description = "Federation Cross-Module Search"

    SEARCH_SURFACES = (
        (
            "federation.competition.edition",
            "name",
            "/odoo/action-sports_federation_competition_core.action_competition_overview/%s",
        ),
        (
            "federation.tournament",
            "name",
            "/odoo/action-sports_federation_tournament.action_federation_tournament/%s",
        ),
        (
            "federation.team",
            "name",
            "/odoo/action-sports_federation_base.action_federation_team/%s",
        ),
        (
            "federation.registration.window",
            "name",
            "/odoo/action-sports_federation_registration.action_registration_desk/%s",
        ),
        (
            "federation.schedule",
            "name",
            "/odoo/action-sports_federation_scheduling.action_schedule_planner_competition/%s",
        ),
        (
            "federation.match",
            "display_name",
            "/odoo/action-sports_federation_tournament.action_federation_match/%s",
        ),
    )

    @api.model
    def search_everywhere(self, term, limit_per_model=5):
        term = (term or "").strip()
        if len(term) < 2:
            return []
        results = []
        for model_name, field_name, url_template in self.SEARCH_SURFACES:
            model = self.env.get(model_name)
            if model is None or field_name not in model._fields:
                continue
            records = model.sudo().search(
                [(field_name, "ilike", term)], limit=limit_per_model
            )
            results.extend(
                {
                    "model": model_name,
                    "type": model._description,
                    "name": record.display_name,
                    "url": url_template % record.id,
                }
                for record in records
            )
        return sorted(results, key=lambda item: (item["type"], item["name"].lower()))
