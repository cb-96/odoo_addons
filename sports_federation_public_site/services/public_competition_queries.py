from odoo import _, fields, models
from odoo.exceptions import ValidationError


class PublicCompetitionQueries(models.AbstractModel):
    _name = "federation.public.competition.queries"
    _description = "Public Competition Queries"

    def public_domain(self, archived=False):
        states = ("finished", "archived") if archived else ("active", "finished")
        return [
            ("website_published", "=", True),
            ("engine_state", "in", states),
            ("active", "=", True),
        ]

    def list_editions(self, archived=False, search=None, season_id=None):
        domain = self.public_domain(archived=archived)
        if search:
            domain.append(("name", "ilike", search.strip()))
        if season_id:
            domain.append(("season_id", "=", int(season_id)))
        return (
            self.env["federation.competition.edition"]
            .sudo()
            .search(domain, order="public_sort_sequence, date_start desc, id desc")
            .filtered(lambda edition: bool(self.public_divisions(edition)))
        )

    def resolve_edition(self, slug):
        edition = (
            self.env["federation.competition.edition"]
            .sudo()
            .search(
                self.public_domain(archived=False) + [("public_slug", "=", slug)],
                limit=1,
            )
        )
        if not edition:
            edition = (
                self.env["federation.competition.edition"]
                .sudo()
                .search(
                    [
                        ("website_published", "=", True),
                        ("engine_state", "=", "archived"),
                        ("public_slug", "=", slug),
                    ],
                    limit=1,
                )
            )
        return edition

    def public_divisions(self, edition):
        return edition.tournament_ids.filtered(
            lambda division: division.active
            and division.website_published
            and division.edition_id == edition
        ).sorted(lambda division: (division.name or "", division.id))

    def edition_summary(self, edition):
        divisions = self.public_divisions(edition)
        matchdays = (
            self.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("edition_id", "=", edition.id),
                    ("current_publication_id.state", "=", "live"),
                ],
                order="date,id",
            )
        )
        today = fields.Date.context_today(self)
        next_matchday = matchdays.filtered(lambda m: m.date >= today)[:1]
        return {
            "edition": edition,
            "divisions": divisions,
            "next_matchday": next_matchday,
            "matchdays": matchdays,
            "current_stage": self.env["federation.public.format.queries"].current_stage(
                edition
            ),
        }

    def assert_publishable(self, edition):
        errors = []
        if not edition.public_slug:
            errors.append(_("configure a public slug"))
        if not edition.tournament_ids.filtered(
            lambda d: d.website_published and d.edition_id == edition
        ):
            errors.append(_("publish at least one division"))
        if edition.engine_state not in ("active", "finished", "archived"):
            errors.append(
                _("move the competition engine to Active, Finished or Archived")
            )
        if errors:
            raise ValidationError(
                _("The edition cannot be published yet: %s") % "; ".join(errors)
            )
        return True
