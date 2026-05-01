import logging

from odoo import models, _
from odoo.exceptions import UserError

from odoo.addons.sports_federation_tournament.workflow_states import (
    TOURNAMENT_STATES_ACTIVE,
)

_logger = logging.getLogger(__name__)


class BaseScheduleService(models.AbstractModel):
    """Shared guard and utility methods for schedule generation services.

    Both ``federation.round.robin.service`` and ``federation.knockout.service``
    inherit this model so that the overwrite/check guard, the tournament-state
    guard, and the participant minimum guard are defined once.
    """

    _name = "federation.base.schedule.service"
    _description = "Base Schedule Generation Service"

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_tournament_state(self, tournament):
        """Raise if tournament is not in a state that allows match generation."""
        if tournament.state not in TOURNAMENT_STATES_ACTIVE:
            raise UserError(
                _("Tournament must be Open or In Progress to generate matches.")
            )

    def _validate_participant_count(self, participants, minimum=2):
        """Raise if too few participants are supplied."""
        if len(participants) < minimum:
            raise UserError(
                _(
                    "At least %d participants are required to generate matches.",
                    minimum,
                )
            )

    # ------------------------------------------------------------------
    # Overwrite / check guard  (group is optional — knockout doesn't use it)
    # ------------------------------------------------------------------

    def _check_existing_matches(self, stage, group=None):
        """Raise if matches already exist in this stage/group."""
        domain = [("stage_id", "=", stage.id)]
        if group:
            domain.append(("group_id", "=", group.id))
        if self.env["federation.match"].search(domain, limit=1):
            raise UserError(
                _(
                    "Existing matches found in this stage/group. "
                    "Enable overwrite mode to replace them."
                )
            )

    def _clear_existing_matches(self, stage, group=None):
        """Delete all matches in this stage/group."""
        domain = [("stage_id", "=", stage.id)]
        if group:
            domain.append(("group_id", "=", group.id))
        self.env["federation.match"].search(domain).unlink()
