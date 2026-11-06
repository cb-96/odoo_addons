"""Hide rosters whose competitions are all archived.

A competition is archived when it is over, so its rosters, roster tasks and
"create roster" reminders have no purpose any more.

Rosters belong to a team and a season, optionally to one competition, not to a
specific competition edition.  A roster is hidden when the team takes part in
at least one division that season and every such division is archived (the
division itself, or its whole competition).  A roster linked to a competition
only looks at that competition's divisions.  A team that still plays in an
active competition that season keeps its roster.
"""

from collections import defaultdict

from odoo import api, fields, models

ROSTER_MODELS = {
    "federation.team.roster": "id",
    "federation.team.roster.line": "roster_id",
}


class FederationPortalArchiveScopeRosters(models.AbstractModel):
    _inherit = "federation.portal.archive.scope"

    @api.model
    def _team_participations(self, team_ids):
        """Return ``{(team_id, season_id): {division: competition_id}}``."""
        env = self.env
        Division = env["federation.tournament"].sudo().with_context(active_test=False)
        pairs = set()
        participants = (
            env["federation.tournament.participant"]
            .sudo()
            .with_context(active_test=False)
            .search([("team_id", "in", team_ids)])
        )
        pairs.update((p.team_id.id, p.tournament_id.id) for p in participants)
        entries = (
            env["federation.competition.entry"]
            .sudo()
            .search([("team_id", "in", team_ids), ("state", "!=", "withdrawn")])
        )
        pairs.update((e.team_id.id, e.window_id.division_id.id) for e in entries)
        lines = (
            env["federation.participant.set.line"]
            .sudo()
            .search(
                [
                    ("team_id", "in", team_ids),
                    ("participant_set_id.state", "=", "finalized"),
                ]
            )
        )
        pairs.update(
            (line.team_id.id, line.participant_set_id.division_id.id) for line in lines
        )
        divisions = Division.browse(
            {division_id for _team, division_id in pairs if division_id}
        )
        info = {
            division.id: (
                division.season_id.id or division.edition_id.season_id.id,
                division.competition_id.id or division.edition_id.competition_id.id,
            )
            for division in divisions
        }
        result = defaultdict(dict)
        for team_id, division_id in pairs:
            if division_id in info:
                season_id, competition_id = info[division_id]
                result[(team_id, season_id)][division_id] = competition_id
        return result

    @api.model
    def _hidden_team_season_scope(self):
        """Teams/seasons whose divisions are all archived.

        Returns ``(team_ids, participations, hidden_division_ids)``; empty when
        nothing is archived.
        """
        hidden_divisions = set(self.hidden_division_ids())
        if not hidden_divisions:
            return [], {}, hidden_divisions
        Participant = self.env["federation.tournament.participant"].sudo()
        team_ids = set(
            Participant.with_context(active_test=False)
            .search([("tournament_id", "in", list(hidden_divisions))])
            .mapped("team_id")
            .ids
        )
        team_ids.update(
            self.env["federation.competition.entry"]
            .sudo()
            .search([("window_id.division_id", "in", list(hidden_divisions))])
            .mapped("team_id")
            .ids
        )
        team_ids.update(
            self.env["federation.participant.set.line"]
            .sudo()
            .search([("participant_set_id.division_id", "in", list(hidden_divisions))])
            .mapped("team_id")
            .ids
        )
        if not team_ids:
            return [], {}, hidden_divisions
        return (
            list(team_ids),
            self._team_participations(list(team_ids)),
            hidden_divisions,
        )

    @staticmethod
    def _all_hidden(divisions, hidden_divisions):
        return bool(divisions) and set(divisions) <= hidden_divisions

    @api.model
    def hidden_roster_ids(self):
        team_ids, participations, hidden_divisions = self._hidden_team_season_scope()
        if not team_ids:
            return []
        rosters = (
            self.env["federation.team.roster"]
            .sudo()
            .with_context(active_test=False)
            .search([("team_id", "in", team_ids)])
        )
        hidden = []
        for roster in rosters:
            divisions = participations.get((roster.team_id.id, roster.season_id.id), {})
            if roster.competition_id:
                divisions = {
                    division_id: competition_id
                    for division_id, competition_id in divisions.items()
                    if competition_id == roster.competition_id.id
                }
            if self._all_hidden(divisions, hidden_divisions):
                hidden.append(roster.id)
        return hidden

    @api.model
    def hidden_registration_ids(self):
        """Season registrations whose team only plays archived competitions."""
        team_ids, participations, hidden_divisions = self._hidden_team_season_scope()
        if not team_ids:
            return []
        registrations = (
            self.env["federation.season.registration"]
            .sudo()
            .search([("team_id", "in", team_ids)])
        )
        return [
            registration.id
            for registration in registrations
            if self._all_hidden(
                participations.get(
                    (registration.team_id.id, registration.season_id.id), {}
                ),
                hidden_divisions,
            )
        ]

    @api.model
    def exclusion_domain(self, model_name):
        domain = super().exclusion_domain(model_name)
        if model_name in ROSTER_MODELS:
            roster_ids = self.hidden_roster_ids()
            if roster_ids:
                domain = domain + [(ROSTER_MODELS[model_name], "not in", roster_ids)]
        elif model_name == "federation.season.registration":
            registration_ids = self.hidden_registration_ids()
            if registration_ids:
                domain = domain + [("id", "not in", registration_ids)]
        elif model_name == "federation.operation.task":
            roster_ids = self.hidden_roster_ids()
            if roster_ids:
                domain = domain + [("roster_id", "not in", roster_ids)]
            registration_ids = self.hidden_registration_ids()
            if registration_ids:
                domain = domain + [
                    "!",
                    "&",
                    ("source_model", "=", "federation.season.registration"),
                    ("source_record_id", "in", registration_ids),
                ]
        return domain

    @api.model
    def close_tasks_for_divisions(self, division_ids):
        """Also close roster and registration tasks that became hidden."""
        closed = super().close_tasks_for_divisions(division_ids)
        roster_ids = self.hidden_roster_ids()
        registration_ids = self.hidden_registration_ids()
        if not roster_ids and not registration_ids:
            return closed
        domain = []
        if roster_ids:
            domain = [("roster_id", "in", roster_ids)]
        if registration_ids:
            registration_domain = [
                "&",
                ("source_model", "=", "federation.season.registration"),
                ("source_record_id", "in", registration_ids),
            ]
            domain = (
                (["|"] + domain + registration_domain)
                if domain
                else registration_domain
            )
        tasks = (
            self.env["federation.operation.task"]
            .sudo()
            .search([("state", "!=", "done")] + domain)
        )
        if tasks:
            tasks.write({"state": "done", "completed_on": fields.Datetime.now()})
        return closed + len(tasks)


class TeamRosterArchiveScope(models.Model):
    _inherit = "federation.team.roster"

    @api.model
    def _portal_get_scope_domain(self, user=None):
        domain = super()._portal_get_scope_domain(user=user)
        if domain == [("id", "=", False)]:
            # Callers compare against this sentinel to show the empty state.
            return domain
        return domain + self.env["federation.portal.archive.scope"].exclusion_domain(
            self._name
        )

    def _portal_assert_scope_access(self, user=None):
        result = super()._portal_assert_scope_access(user=user)
        self.env["federation.portal.archive.scope"].assert_visible(self)
        return result
