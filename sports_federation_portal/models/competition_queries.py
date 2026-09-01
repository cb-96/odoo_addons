from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class FederationPortalcurrentScope(models.AbstractModel):
    _name = "federation.portal.scope"
    _description = "Portal Scope Service"

    @api.model
    def team_domain(self, user=None):
        user = user or self.env.user
        if not user.share and user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            return []
        team_ids = user.portal_team_scope_ids.ids
        club_ids = user.portal_club_scope_ids.ids
        if team_ids and club_ids:
            return ["|", ("id", "in", team_ids), ("club_id", "in", club_ids)]
        if team_ids:
            return [("id", "in", team_ids)]
        if club_ids:
            return [("club_id", "in", club_ids)]
        return [("id", "=", False)]

    @api.model
    def teams(self, user=None):
        return self.env["federation.team"].sudo().search(self.team_domain(user=user))

    @api.model
    def assert_team(self, team, user=None):
        if not team or not self.env["federation.team"].sudo().search_count(
            [("id", "=", team.id)] + self.team_domain(user=user)
        ):
            raise AccessError(_("You do not have access to this team."))
        return team


class FederationPortalCompetitionQueries(models.AbstractModel):
    _name = "federation.portal.competition.queries"
    _description = "Portal Competition Projections"

    def _scope(self):
        return self.env["federation.portal.scope"]

    @api.model
    def visible_editions(self, user=None):
        teams = self._scope().teams(user=user)
        if not teams:
            return self.env["federation.competition.edition"]
        edition_ids = set(
            self.env["federation.competition.entry"]
            .sudo()
            .search([("team_id", "in", teams.ids), ("state", "!=", "withdrawn")])
            .mapped("edition_id")
            .ids
        )
        edition_ids.update(
            self.env["federation.participant.set.line"]
            .sudo()
            .search(
                [
                    ("team_id", "in", teams.ids),
                    ("participant_set_id.state", "=", "finalized"),
                ]
            )
            .mapped("participant_set_id.edition_id")
            .ids
        )
        return (
            self.env["federation.competition.edition"]
            .sudo()
            .search([("id", "in", list(edition_ids))], order="date_start desc,id desc")
        )

    @api.model
    def assert_visible_edition(self, edition_id, user=None):
        edition = self.visible_editions(user=user).filtered(
            lambda item: item.id == int(edition_id)
        )
        if not edition:
            raise AccessError(_("You do not have access to this competition."))
        return edition[:1]

    def _visible_teams_for_edition(self, edition, user=None):
        scoped = self._scope().teams(user=user)
        participant_team_ids = (
            self.env["federation.participant.set.line"]
            .sudo()
            .search(
                [
                    ("participant_set_id.edition_id", "=", edition.id),
                    ("participant_set_id.state", "=", "finalized"),
                    ("team_id", "in", scoped.ids),
                ]
            )
            .mapped("team_id")
        )
        entry_team_ids = (
            self.env["federation.competition.entry"]
            .sudo()
            .search(
                [
                    ("edition_id", "=", edition.id),
                    ("team_id", "in", scoped.ids),
                    ("state", "!=", "withdrawn"),
                ]
            )
            .mapped("team_id")
        )
        return participant_team_ids | entry_team_ids

    @api.model
    def competition_card(self, edition, user=None):
        teams = self._visible_teams_for_edition(edition, user=user)
        days = (
            self.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("edition_id", "=", edition.id),
                    ("current_publication_id.state", "=", "live"),
                ],
                order="date asc,id asc",
            )
        )
        visible_match_domain = [
            (
                "schedule_publication_id",
                "in",
                days.mapped("current_publication_id").ids,
            ),
            "|",
            ("home_team_id", "in", teams.ids),
            ("away_team_id", "in", teams.ids),
        ]
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(visible_match_domain, order="date_scheduled asc,id asc")
            if days and teams
            else self.env["federation.match"]
        )
        active = days.filtered(lambda day: day.state == "open")
        unfinished = matches.filtered(
            lambda match: match.state not in ("done", "cancelled")
        )
        if edition.state in ("closed", "cancelled") or not unfinished and matches:
            label, tone = _("Finished"), "secondary"
        elif active:
            label, tone = _("Live"), "danger"
        elif days:
            label, tone = _("Ready"), "success"
        else:
            label, tone = _("Preparing"), "warning"
        return {
            "edition": edition,
            "teams": teams,
            "status_label": label,
            "status_tone": tone,
            "next_match": unfinished[:1],
            "published_matchday_count": len(days),
            "result_follow_up_count": len(
                matches.filtered(
                    lambda m: m.state == "done"
                    and m.result_state
                    in ("draft", "submitted", "verified", "contested", "corrected")
                )
            ),
        }

    @api.model
    def list_cards(self, user=None):
        return [
            self.competition_card(edition, user=user)
            for edition in self.visible_editions(user=user)
        ]

    @api.model
    def detail(self, edition_id, user=None):
        edition = self.assert_visible_edition(edition_id, user=user)
        card = self.competition_card(edition, user=user)
        teams = card["teams"]
        participant_sets = (
            self.env["federation.participant.set"]
            .sudo()
            .search([("edition_id", "=", edition.id), ("state", "=", "finalized")])
        )
        entries = (
            self.env["federation.competition.entry"]
            .sudo()
            .search([("edition_id", "=", edition.id), ("team_id", "in", teams.ids)])
        )
        matchdays = (
            self.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("edition_id", "=", edition.id),
                    ("current_publication_id.state", "=", "live"),
                ],
                order="date asc,id asc",
            )
        )
        publications = matchdays.mapped("current_publication_id")
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("schedule_publication_id", "in", publications.ids),
                    "|",
                    ("home_team_id", "in", teams.ids),
                    ("away_team_id", "in", teams.ids),
                ],
                order="date_scheduled asc,id asc",
            )
            if publications and teams
            else self.env["federation.match"]
        )
        standings = (
            self.env["federation.standing"]
            .sudo()
            .search(
                [("tournament_id", "in", participant_sets.mapped("division_id").ids)]
            )
        )
        return {
            **card,
            "participant_sets": participant_sets,
            "entries": entries,
            "matchdays": matchdays,
            "matches": matches,
            "standings": standings,
        }


class FederationPortalMatchdayQueries(models.AbstractModel):
    _name = "federation.portal.matchday.queries"
    _description = "Portal Match-Day Projections"

    def _scope(self):
        return self.env["federation.portal.scope"]

    @api.model
    def visible_matchdays(self, user=None):
        teams = self._scope().teams(user=user)
        if not teams:
            return self.env["federation.matchday"]
        publication_ids = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("schedule_publication_id.state", "=", "live"),
                    "|",
                    ("home_team_id", "in", teams.ids),
                    ("away_team_id", "in", teams.ids),
                ]
            )
            .mapped("schedule_publication_id")
            .ids
        )
        return (
            self.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("current_publication_id", "in", publication_ids),
                    ("current_publication_id.state", "=", "live"),
                ],
                order="date asc,id asc",
            )
        )

    @api.model
    def detail(self, matchday_id, user=None, manager=False):
        day = self.env["federation.matchday"].sudo().browse(int(matchday_id)).exists()
        if (
            not day
            or not day.current_publication_id
            or day.current_publication_id.state != "live"
        ):
            raise AccessError(_("This match day has no visible live publication."))
        teams = self._scope().teams(user=user)
        if manager and not (user or self.env.user).share:
            matches = (
                self.env["federation.match"]
                .sudo()
                .search(
                    [("schedule_publication_id", "=", day.current_publication_id.id)],
                    order="date_scheduled asc,id asc",
                )
            )
        else:
            matches = (
                self.env["federation.match"]
                .sudo()
                .search(
                    [
                        ("schedule_publication_id", "=", day.current_publication_id.id),
                        "|",
                        ("home_team_id", "in", teams.ids),
                        ("away_team_id", "in", teams.ids),
                    ],
                    order="date_scheduled asc,id asc",
                )
            )
        if not matches:
            raise AccessError(_("You do not have access to this match day."))
        return {
            "matchday": day,
            "publication": day.current_publication_id,
            "session": day.active_session_id,
            "matches": matches,
            "courts": day.court_status_ids,
            "incidents": day.incident_ids,
            "deviations": day.deviation_ids,
        }
