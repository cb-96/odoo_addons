"""Keep archived competitions out of the portal.

Archiving a competition (``federation.competition.edition``) or a division
(``federation.tournament``) only sets ``active = False`` on that record.  The
entries, matches, lineups, referee duties, game days and tasks inside it stay
active, and the portal reads them with elevated rights, so they kept showing
up and tasks were even regenerated on every visit.

This model is the single definition of "belongs to an archived competition".
The portal privilege boundary, the task projection and the few controllers
that read records directly all use it.  Nothing is deleted or changed in the
archived competition itself: restoring it makes everything visible again.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

# Model -> (field path to the division or competition, kind)
ARCHIVE_PATHS = {
    "federation.competition.edition": ("id", "edition"),
    "federation.tournament": ("id", "division"),
    "federation.registration.window": ("division_id", "division"),
    "federation.competition.entry": ("window_id.division_id", "division"),
    "federation.tournament.participant": ("tournament_id", "division"),
    "federation.match": ("tournament_id", "division"),
    "federation.match.sheet": ("match_id.tournament_id", "division"),
    "federation.match.referee": ("match_id.tournament_id", "division"),
    "federation.match.club.referee.duty": ("match_id.tournament_id", "division"),
    "federation.standing": ("tournament_id", "division"),
    "federation.matchday": ("edition_id", "edition"),
    "federation.operation.task": ("tournament_id", "division"),
}


class FederationPortalArchiveScope(models.AbstractModel):
    _name = "federation.portal.archive.scope"
    _description = "Portal Exclusion of Archived Competitions"

    @api.model
    def hidden_edition_ids(self):
        return (
            self.env["federation.competition.edition"]
            .sudo()
            .with_context(active_test=False)
            .search([("active", "=", False)])
            .ids
        )

    @api.model
    def hidden_division_ids(self, edition_ids=None):
        """Archived divisions and every division of an archived competition."""
        if edition_ids is None:
            edition_ids = self.hidden_edition_ids()
        domain = [("active", "=", False)]
        if edition_ids:
            domain = ["|", ("active", "=", False), ("edition_id", "in", edition_ids)]
        return (
            self.env["federation.tournament"]
            .sudo()
            .with_context(active_test=False)
            .search(domain)
            .ids
        )

    @api.model
    def exclusion_domain(self, model_name):
        """Domain removing records of archived competitions; [] if unrelated."""
        spec = ARCHIVE_PATHS.get(model_name)
        if not spec or model_name not in self.env:
            return []
        path, kind = spec
        edition_ids = self.hidden_edition_ids()
        ids = (
            edition_ids if kind == "edition" else self.hidden_division_ids(edition_ids)
        )
        if not ids:
            return []
        return [(path, "not in", ids)]

    @api.model
    def filter_visible(self, records):
        """Return ``records`` without those belonging to an archived competition."""
        if not records:
            return records
        domain = self.exclusion_domain(records._name)
        if not domain:
            return records
        visible_ids = set(
            records.sudo()
            .with_context(active_test=False)
            .search(domain + [("id", "in", records.ids)])
            .ids
        )
        return records.filtered(lambda record: record.id in visible_ids)

    @api.model
    def assert_visible(self, records):
        """Raise when any record belongs to an archived competition."""
        if records and self.filter_visible(records) != records:
            raise AccessError(_("This competition is no longer available."))
        return records

    @api.model
    def close_tasks_for_divisions(self, division_ids):
        """Close open tasks of archived divisions so no queue or digest shows them.

        Tasks are projections; the next sync reopens them if the competition
        is restored.
        """
        if not division_ids:
            return 0
        tasks = (
            self.env["federation.operation.task"]
            .sudo()
            .search(
                [("tournament_id", "in", list(division_ids)), ("state", "!=", "done")]
            )
        )
        if tasks:
            tasks.write({"state": "done", "completed_on": fields.Datetime.now()})
        return len(tasks)
