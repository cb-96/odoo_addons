import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary

_logger = logging.getLogger(__name__)

MAX_DETAIL_LINES = 5


class FederationMatchdayReadiness(models.AbstractModel):
    """The single authoritative answer to "Can this game day run?".

    The planner, the backend match-day screen, the live workspace and the
    release tests all call :meth:`evaluate`. Addons that own a part of the game
    day extend :meth:`_readiness_providers` with one provider each; nothing else
    calculates match-day readiness.
    """

    _name = "federation.matchday.readiness"
    _description = "Authoritative Match-Day Readiness"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def evaluate(self, matchday):
        """Return the full readiness projection of one game day."""
        matchday.ensure_one()
        matchday.check_access("read")
        scope = self._readiness_scope(matchday)
        components = [
            self._run_provider(key, method, scope)
            for key, method in self._readiness_providers()
        ]
        return self._present(scope, vocabulary.project(components))

    @api.model
    def brief(self, matchday):
        """Return the projection without owners and destinations.

        Used by surfaces that are shown to court operators, who need to know
        what is open but should not receive internal assignments or links.
        """
        result = self.evaluate(matchday)
        return {
            "overall": result["overall"],
            "overall_label": result["overall_label"],
            "can_run": result["can_run"],
            "headline": result["headline"],
            "components": [
                {
                    key: component[key]
                    for key in ("key", "label", "status", "status_label", "summary")
                }
                for component in result["components"]
            ],
            "blockers": [
                {
                    key: blocker[key]
                    for key in (
                        "component",
                        "status",
                        "status_label",
                        "problem",
                        "action",
                    )
                }
                for blocker in result["blockers"][:MAX_DETAIL_LINES]
            ],
        }

    @api.model
    def component_keys(self):
        """Return the component keys registered by the installed addons."""
        return [key for key, _method in self._readiness_providers()]

    # ------------------------------------------------------------------
    # Extension points
    # ------------------------------------------------------------------

    @api.model
    def _readiness_providers(self):
        """Return ``(component key, provider method name)`` pairs."""
        return [
            ("schedule", "_readiness_schedule"),
            ("courts", "_readiness_courts"),
        ]

    @api.model
    def _readiness_scope(self, matchday):
        """Collect the records every provider evaluates."""
        matchday = matchday.sudo()
        Match = matchday.env["federation.match"]
        publication = matchday.current_publication_id
        matches = Match
        if publication:
            matches = Match.search([("schedule_publication_id", "=", publication.id)])
        matches = matches.filtered(
            lambda match: match.state != "cancelled"
            and match.operational_status not in ("cancelled", "postponed")
        )
        kickoffs = [
            fields.Datetime.to_datetime(match.date_scheduled)
            for match in matches
            if match.date_scheduled
        ]
        return {
            "matchday": matchday,
            "publication": publication,
            "matches": matches,
            "teams": matches.mapped("home_team_id") | matches.mapped("away_team_id"),
            "first_kickoff": min(kickoffs) if kickoffs else False,
        }

    # ------------------------------------------------------------------
    # Helpers shared by the providers
    # ------------------------------------------------------------------

    @api.model
    def _component_labels(self):
        return {
            "schedule": _("Schedule"),
            "rosters": _("Rosters"),
            "lineups": _("Line-ups"),
            "officials": _("Officials"),
            "courts": _("Courts"),
            "eligibility": _("Eligibility"),
            "compliance": _("Compliance"),
        }

    @api.model
    def _count_text(self, count, singular, plural):
        """Pick the singular or plural sentence and fill in the count."""
        return (singular if count == 1 else plural) % {"count": count}

    @api.model
    def _iso(self, value):
        """Serialise a date or datetime for JSON and display."""
        if not value:
            return None
        if hasattr(value, "hour"):
            return fields.Datetime.to_string(value)
        if hasattr(value, "isoformat"):
            return fields.Date.to_string(value)
        return str(value)

    @api.model
    def _earliest(self, values):
        values = [value for value in values if value]
        return min(values) if values else None

    @api.model
    def _ready_component(self, key, summary=None, status=vocabulary.READY):
        label = self.env["federation.readiness.vocabulary"].label(status)
        return vocabulary.make_component(key, status, summary or label)

    @api.model
    def _matchday_destination(self, scope):
        return vocabulary.make_destination(
            "federation.matchday", res_id=scope["matchday"].id
        )

    @api.model
    def _records_destination(self, records):
        """Point at the one record, or at the list of the affected records."""
        if len(records) == 1:
            return vocabulary.make_destination(records._name, res_id=records.id)
        return vocabulary.make_destination(
            records._name, domain=[("id", "in", records.ids)], view="list"
        )

    @api.model
    def _details(self, lines):
        lines = [line for line in lines if line]
        extra = len(lines) - MAX_DETAIL_LINES
        lines = lines[:MAX_DETAIL_LINES]
        if extra > 0:
            lines.append(_("… and %(count)s more", count=extra))
        return lines

    @api.model
    def _counter_component(self, key, ready, total, blockers):
        """Build a "7 / 8 ready" component from its blockers."""
        if blockers:
            status = vocabulary.aggregate(blocker["status"] for blocker in blockers)
            summary = vocabulary.format_ratio(ready, total)
        else:
            status = vocabulary.READY
            summary = self.env["federation.readiness.vocabulary"].label(status)
        return vocabulary.make_component(
            key, status, summary, blockers=blockers, ready=ready, total=total
        )

    @api.model
    def _run_provider(self, key, method, scope):
        """Run one provider; a failing provider must never look ready."""
        day = scope["matchday"]
        if day.state == "closed" and key != "schedule":
            return self._ready_component(key, _("Closed"), vocabulary.COMPLETE)
        if day.state == "cancelled":
            return self._ready_component(key, _("Cancelled"), vocabulary.NOT_APPLICABLE)
        try:
            with self.env.cr.savepoint():
                return getattr(self, method)(scope)
        except Exception:  # pylint: disable=broad-except
            _logger.exception("Match-day readiness provider %s failed", key)
        label = self._component_labels().get(key, key)
        component = vocabulary.make_component(
            key,
            vocabulary.BLOCKED,
            _("Could not be determined"),
            blockers=[
                vocabulary.make_blocker(
                    key="%s-unavailable" % key,
                    status=vocabulary.BLOCKED,
                    problem=_("The %(component)s check could not be completed.")
                    % {"component": label},
                    action=_(
                        "Ask an administrator to check the server log, then "
                        "reopen this page."
                    ),
                    destination=self._matchday_destination(scope),
                    owner=_("System administrator"),
                )
            ],
        )
        component["error"] = True
        return component

    # ------------------------------------------------------------------
    # Providers owned by this addon
    # ------------------------------------------------------------------

    @api.model
    def _readiness_schedule(self, scope):
        day = scope["matchday"]
        publication = scope["publication"]
        if day.state == "closed":
            return self._ready_component("schedule", _("Closed"), vocabulary.COMPLETE)
        if day.state == "open":
            return self._ready_component("schedule", _("Live operations are active"))
        live = publication and publication.state == "live"
        if live and scope["matches"]:
            return self._ready_component("schedule", _("Published"))
        deadline = self._iso(day.date)
        if live:
            return self._schedule_component(
                vocabulary.ACTION_NEEDED,
                _("No matches"),
                _("The live publication contains no operational matches."),
                _("Review the published schedule and republish it."),
                vocabulary.make_destination(
                    "federation.schedule", res_id=publication.schedule_id.id
                ),
                _("Competition organiser"),
                deadline,
            )
        schedule = day.env["federation.schedule"].search(
            [("matchday_id", "=", day.id), ("state", "!=", "superseded")],
            order="id desc",
            limit=1,
        )
        if not schedule:
            return self._schedule_component(
                vocabulary.ACTION_NEEDED,
                _("No schedule"),
                _("No schedule exists for this game day yet."),
                _("Generate the schedule for this game day."),
                self._matchday_destination(scope),
                _("Competition organiser"),
                deadline,
            )
        destination = vocabulary.make_destination(
            "federation.schedule", res_id=schedule.id
        )
        texts = {
            "draft": (
                vocabulary.ACTION_NEEDED,
                _("The schedule is still a draft."),
                _("Submit the schedule for review."),
                _("Competition organiser"),
            ),
            "ready_for_review": (
                vocabulary.WAITING_REVIEW,
                _("The schedule is waiting for an independent review."),
                _("Review and approve the schedule."),
                _("Schedule reviewer"),
            ),
            "changes_requested": (
                vocabulary.ACTION_NEEDED,
                _("The reviewer asked for changes to the schedule."),
                _("Update the schedule and submit it again."),
                _("Competition organiser"),
            ),
            "approved": (
                vocabulary.ACTION_NEEDED,
                _("The approved schedule has not been published."),
                _("Publish the schedule."),
                _("Competition organiser"),
            ),
        }
        status, problem, action, owner = texts.get(
            schedule.state,
            (
                vocabulary.ACTION_NEEDED,
                _("The schedule has no live publication."),
                _("Review the schedule and publish it again."),
                _("Competition organiser"),
            ),
        )
        return self._schedule_component(
            status,
            self.env["federation.readiness.vocabulary"].label(status),
            problem,
            action,
            destination,
            owner,
            deadline,
        )

    @api.model
    def _schedule_component(
        self, status, summary, problem, action, destination, owner, deadline
    ):
        return vocabulary.make_component(
            "schedule",
            status,
            summary,
            blockers=[
                vocabulary.make_blocker(
                    key="schedule",
                    status=status,
                    problem=problem,
                    action=action,
                    destination=destination,
                    owner=owner,
                    deadline=deadline,
                )
            ],
        )

    @api.model
    def _readiness_courts(self, scope):
        day = scope["matchday"]
        matches = scope["matches"]
        if not matches:
            return self._ready_component(
                "courts", _("No matches"), vocabulary.NOT_APPLICABLE
            )
        slots = {
            match.id: match.operational_slot_id or match.published_slot_id
            for match in matches
        }
        courts = self.env["federation.playing.area"].browse(
            [slot.court_id.id for slot in slots.values() if slot.court_id]
        )
        unavailable = day.court_status_ids.filtered(
            lambda status: status.state == "unavailable" and status.court_id in courts
        )
        without_court = matches.filtered(lambda match: not slots[match.id].court_id)
        incidents = day.incident_ids.filtered(lambda incident: not incident.resolved)
        deadline = self._iso(scope["first_kickoff"] or day.date)
        blockers = []
        if unavailable:
            blockers.append(
                vocabulary.make_blocker(
                    key="courts-unavailable",
                    status=vocabulary.BLOCKED,
                    problem=self._count_text(
                        len(unavailable),
                        _("%(count)s court is unavailable."),
                        _("%(count)s courts are unavailable."),
                    ),
                    action=_("Update the court status or move the affected matches."),
                    destination=self._matchday_destination(scope),
                    owner=_("Match-day manager"),
                    deadline=deadline,
                    count=len(unavailable),
                    details=self._details(unavailable.mapped("court_id.display_name")),
                )
            )
        if without_court:
            blockers.append(
                vocabulary.make_blocker(
                    key="courts-unassigned",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(without_court),
                        _("%(count)s match has no court."),
                        _("%(count)s matches have no court."),
                    ),
                    action=_("Assign a court to each match in the schedule."),
                    destination=self._records_destination(without_court),
                    owner=_("Competition organiser"),
                    deadline=deadline,
                    count=len(without_court),
                    details=self._details(without_court.mapped("display_name")),
                )
            )
        if incidents:
            blockers.append(
                vocabulary.make_blocker(
                    key="courts-incidents",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(incidents),
                        _("%(count)s match-day incident is unresolved."),
                        _("%(count)s match-day incidents are unresolved."),
                    ),
                    action=_("Resolve the incident or record how it was handled."),
                    destination=self._records_destination(incidents),
                    owner=_("Match-day manager"),
                    deadline=deadline,
                    count=len(incidents),
                    details=self._details(incidents.mapped("description")),
                )
            )
        total = len(courts)
        ready = total - len(unavailable)
        if blockers:
            status = vocabulary.aggregate(blocker["status"] for blocker in blockers)
            summary = (
                vocabulary.format_ratio(ready, total)
                if total
                else self.env["federation.readiness.vocabulary"].label(status)
            )
        else:
            status = vocabulary.READY
            summary = self.env["federation.readiness.vocabulary"].label(status)
        return vocabulary.make_component(
            "courts", status, summary, blockers=blockers, ready=ready, total=total
        )

    # ------------------------------------------------------------------
    # Presentation
    # ------------------------------------------------------------------

    @api.model
    def _present(self, scope, projection):
        day = scope["matchday"]
        words = self.env["federation.readiness.vocabulary"]
        labels = words.labels()
        component_labels = self._component_labels()
        no_owner = _("No owner assigned")
        no_deadline = _("No deadline set")
        components = []
        presented_blockers = {}
        for component in projection["components"]:
            presented = {
                key: component[key]
                for key in ("key", "status", "summary", "ready", "total")
            }
            presented["label"] = component_labels.get(
                component["key"], component["key"]
            )
            presented["status_label"] = labels[component["status"]]
            presented["error"] = bool(component.get("error"))
            presented["blockers"] = []
            for blocker in component["blockers"]:
                item = dict(blocker)
                item["component"] = component["key"]
                item["component_label"] = presented["label"]
                item["status_label"] = labels[blocker["status"]]
                item["owner_label"] = blocker["owner"] or no_owner
                item["deadline_label"] = blocker["deadline"] or no_deadline
                presented["blockers"].append(item)
                presented_blockers[(component["key"], blocker["key"])] = item
            components.append(presented)
        blockers = [
            presented_blockers[(component["key"], blocker["key"])]
            for component in projection["components"]
            for blocker in component["blockers"]
        ]
        blockers.sort(key=vocabulary.blocker_sort_key)
        if projection["can_run"]:
            headline = _("This game day can run.")
        elif projection["overall"] == vocabulary.COMPLETE:
            headline = _("This game day is complete.")
        elif projection["overall"] == vocabulary.NOT_APPLICABLE:
            headline = _("There is nothing to check for this game day.")
        else:
            headline = self._count_text(
                len(blockers),
                _("This game day cannot run yet: %(count)s item needs attention."),
                _("This game day cannot run yet: %(count)s items need attention."),
            )
        return {
            "matchday_id": day.id,
            "matchday_name": day.display_name,
            "date": self._iso(day.date),
            "overall": projection["overall"],
            "overall_label": labels[projection["overall"]],
            "can_run": projection["can_run"],
            "headline": headline,
            "components": components,
            "blockers": blockers,
        }

    @api.model
    def destination_url(self, destination):
        """Return a backend link for a record destination, else ``False``."""
        if destination.get("res_id"):
            return "/odoo/%s/%s" % (destination["model"], destination["res_id"])
        return False

    @api.model
    def render_html(self, result):
        """Render the projection for the backend match-day screen."""
        badge = vocabulary.BADGE_CLASSES
        rows = Markup("").join(
            Markup(
                '<tr><td>%s</td><td><span class="badge %s">%s</span></td>'
                "<td>%s</td></tr>"
            )
            % (
                component["label"],
                badge[component["status"]],
                component["status_label"],
                component["summary"],
            )
            for component in result["components"]
        )
        items = Markup("").join(
            self._render_blocker(item) for item in result["blockers"]
        )
        blockers = (
            Markup('<ul class="list-unstyled">%s</ul>') % items if items else Markup("")
        )
        return (
            Markup('<p><strong>%s</strong></p><table class="table table-sm">')
            % result["headline"]
            + rows
            + Markup("</table>")
            + blockers
        )

    @api.model
    def _render_blocker(self, blocker):
        link = self.destination_url(blocker["destination"])
        action = (
            Markup('<a href="%s">%s</a>') % (link, blocker["action"])
            if link
            else blocker["action"]
        )
        details = Markup("").join(
            Markup("<li>%s</li>") % line for line in blocker["details"]
        )
        return Markup(
            '<li class="mb-2"><span class="badge %s">%s</span> <strong>%s</strong> '
            "%s<br/><small>%s: %s · %s: %s</small>%s</li>"
        ) % (
            vocabulary.BADGE_CLASSES[blocker["status"]],
            blocker["component_label"],
            blocker["problem"],
            action,
            _("Owner"),
            blocker["owner_label"],
            _("Deadline"),
            blocker["deadline_label"],
            Markup('<ul class="small">%s</ul>') % details if details else Markup(""),
        )


class FederationMatchdayReadinessFields(models.Model):
    _inherit = "federation.matchday"

    readiness_overall = fields.Selection(
        vocabulary.SELECTION,
        string="Can this game day run?",
        compute="_compute_readiness_projection",
    )
    readiness_summary = fields.Html(
        string="Readiness",
        compute="_compute_readiness_projection",
        sanitize=False,
    )

    def _compute_readiness_projection(self):
        service = self.env["federation.matchday.readiness"]
        for day in self:
            persisted = day._origin
            if not persisted:
                day.readiness_overall = vocabulary.NOT_APPLICABLE
                day.readiness_summary = False
                continue
            result = service.evaluate(persisted)
            day.readiness_overall = result["overall"]
            day.readiness_summary = service.render_html(result)
