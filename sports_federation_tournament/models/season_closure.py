from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationSeasonClosure(models.Model):
    _inherit = "federation.season"

    closure_checklist = fields.Json(compute="_compute_closure_checklist")
    closure_checklist_html = fields.Html(
        compute="_compute_closure_checklist", sanitize=True
    )
    closure_blocker_count = fields.Integer(compute="_compute_closure_checklist")

    def _closure_checks(self):
        self.ensure_one()
        Match = self.env.get("federation.match")
        matches = (
            Match.search([("tournament_id.season_id", "=", self.id)])
            if Match is not None
            else Match
        )
        checks = [
            {
                "key": "tournaments",
                "label": _("Active competitions"),
                "count": len(
                    self.tournament_ids.filtered(
                        lambda item: item.state not in ("closed", "cancelled")
                    )
                ),
            },
            {
                "key": "matches",
                "label": _("Unfinished matches"),
                "count": (
                    len(
                        matches.filtered(
                            lambda item: item.state not in ("done", "cancelled")
                        )
                    )
                    if matches is not None
                    else 0
                ),
            },
            {
                "key": "results",
                "label": _("Results not approved"),
                "count": (
                    len(
                        matches.filtered(
                            lambda item: item.state == "done"
                            and getattr(item, "result_state", "approved") != "approved"
                        )
                    )
                    if matches is not None
                    else 0
                ),
            },
        ]
        Duty = self.env.get("federation.match.club.referee.duty")
        checks.append(
            {
                "key": "duties",
                "label": _("Unresolved club duties"),
                "count": (
                    Duty.search_count(
                        [
                            ("match_id.tournament_id.season_id", "=", self.id),
                            ("state", "not in", ("confirmed", "rejected")),
                        ]
                    )
                    if Duty is not None
                    else 0
                ),
            }
        )
        Finance = self.env.get("federation.finance.event")
        checks.append(
            {
                "key": "finance",
                "label": _("Open financial obligations"),
                "count": (
                    Finance.search_count(
                        [
                            ("season_id", "=", self.id),
                            "|",
                            ("state", "not in", ("settled", "cancelled")),
                            ("handoff_state", "not in", ("reconciled", "closed")),
                        ]
                    )
                    if Finance is not None
                    else 0
                ),
            }
        )
        Case = self.env.get("federation.disciplinary.case")
        checks.append(
            {
                "key": "discipline",
                "label": _("Open disciplinary cases or appeals"),
                "count": (
                    Case.search_count(
                        [
                            (
                                "incident_ids.match_id.tournament_id.season_id",
                                "=",
                                self.id,
                            ),
                            ("state", "!=", "closed"),
                        ]
                    )
                    if Case is not None
                    else 0
                ),
            }
        )
        return checks

    @api.depends("state", "tournament_ids.state")
    def _compute_closure_checklist(self):
        for season in self:
            if not season.id:
                season.closure_checklist = []
                season.closure_checklist_html = False
                season.closure_blocker_count = 0
                continue
            checks = season._closure_checks()
            season.closure_checklist = checks
            season.closure_blocker_count = sum(item["count"] for item in checks)
            season.closure_checklist_html = "<ul>%s</ul>" % "".join(
                "<li>%s: <strong>%s</strong></li>"
                % (escape(str(item["label"])), item["count"])
                for item in checks
            )

    def action_close(self):
        for season in self:
            checks = season._closure_checks()
            blockers = [item for item in checks if item["count"]]
            if blockers:
                raise ValidationError(
                    _("Resolve the season-closure checklist first:\n%s")
                    % "\n".join(
                        "- %s: %s" % (item["label"], item["count"]) for item in blockers
                    )
                )
        return super().action_close()

    def action_open_next_season_copy(self):
        self.ensure_one()
        wizard = self.env["federation.next.season.copy.wizard"].create(
            {
                "source_season_id": self.id,
                "name": _("%s (next)") % self.name,
                "date_start": self.date_start,
                "date_end": self.date_end,
            }
        )
        return wizard.get_formview_action()


class FederationNextSeasonCopyWizard(models.TransientModel):
    _name = "federation.next.season.copy.wizard"
    _description = "Copy Safe Next-Season Configuration"

    source_season_id = fields.Many2one(
        "federation.season", required=True, readonly=True
    )
    name = fields.Char(required=True)
    code = fields.Char(required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    copy_divisions = fields.Boolean(default=True)

    def action_copy(self):
        self.ensure_one()
        source = self.source_season_id
        if self.date_end <= self.date_start:
            raise ValidationError(_("The new season end must follow its start."))
        season = self.env["federation.season"].create(
            {
                "name": self.name,
                "code": self.code,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "state": "draft",
                "target_club_count": source.target_club_count,
                "target_team_count": source.target_team_count,
                "target_tournament_count": source.target_tournament_count,
                "target_participant_count": source.target_participant_count,
            }
        )
        if self.copy_divisions:
            for division in source.tournament_ids:
                self.env["federation.tournament"].create(
                    {
                        "name": division.name,
                        "category": division.category,
                        "gender": division.gender,
                        "date_start": self.date_start,
                        "date_end": self.date_end,
                        "location": division.location,
                        "season_id": season.id,
                        "tournament_type": division.tournament_type,
                        "max_participants": division.max_participants,
                        "competition_id": division.competition_id.id,
                        "rule_set_id": division.rule_set_id.id,
                        "state": "draft",
                    }
                )
        return season.get_formview_action()
