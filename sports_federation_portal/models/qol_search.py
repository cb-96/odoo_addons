from odoo import api, models
from odoo.fields import Domain


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
    def _club_scope_ids(self):
        representative = self.env.get("federation.club.representative")
        if representative is None:
            return []
        return representative.sudo()._get_clubs_for_user(user=self.env.user).ids

    @api.model
    def _scope_domain(self, model):
        if not self.env.user._is_portal():
            return []
        club_ids = self._club_scope_ids()
        if not club_ids:
            return [("id", "=", 0)]
        candidates = []
        for path in (
            "club_id",
            "team_id.club_id",
            "tournament_id.club_id",
            "tournament_id.competition_edition_id.club_id",
            "competition_edition_id.club_id",
            "edition_id.club_id",
        ):
            if path.split(".", 1)[0] in model._fields:
                candidates.append([(path, "in", club_ids)])
        if not candidates:
            return [("id", "=", 0)]
        domain = list(Domain.OR(candidates))
        if "active" in model._fields:
            domain = list(Domain.AND([domain, [("active", "=", True)]]))
        return domain

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
            domain = list(
                Domain.AND([[(field_name, "ilike", term)], self._scope_domain(model)])
            )
            records = model.search(domain, limit=limit_per_model)
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
