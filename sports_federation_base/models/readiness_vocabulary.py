from odoo import _, api, models

from .. import readiness_vocabulary as vocabulary


class FederationReadinessVocabulary(models.AbstractModel):
    """Translated access to the federation-wide readiness vocabulary.

    Technical models keep their detailed lifecycle states. Volunteer-facing
    surfaces ask this service how a state is called, so the words stay the same
    everywhere: Ready, Action needed, Waiting for review, Blocked, Complete and
    Not applicable.
    """

    _name = "federation.readiness.vocabulary"
    _description = "Federation Readiness Vocabulary"

    @api.model
    def labels(self):
        """Return the translated label of every shared status."""
        return {
            vocabulary.READY: _("Ready"),
            vocabulary.ACTION_NEEDED: _("Action needed"),
            vocabulary.WAITING_REVIEW: _("Waiting for review"),
            vocabulary.BLOCKED: _("Blocked"),
            vocabulary.COMPLETE: _("Complete"),
            vocabulary.NOT_APPLICABLE: _("Not applicable"),
        }

    @api.model
    def label(self, status):
        """Return the translated label of one shared status."""
        return self.labels()[status]

    @api.model
    def status_for(self, domain, state):
        """Map an internal state of ``domain`` to a shared status code."""
        return vocabulary.status_for(domain, state)

    @api.model
    def label_for(self, domain, state):
        """Return the translated shared label of an internal state."""
        return self.label(vocabulary.status_for(domain, state))

    @api.model
    def badge_class(self, status):
        """Return the Bootstrap badge class that goes with a shared status."""
        return vocabulary.BADGE_CLASSES[status]
