from odoo import api, models
from odoo.exceptions import ValidationError

from .journey_event import current_session


class PortalPrivilegeInstrumentation(models.AbstractModel):
    """Count portal commands, their validation errors and retries.

    The journey name is ``<model>.<method>``; no record ids, names or error text
    are stored.
    """

    _inherit = "federation.portal.privilege"

    @api.model
    def portal_call(self, records, method_name, *args, **kwargs):
        journey = "%s.%s" % (records._name, method_name)
        events = self.env["federation.journey.event"]
        session = current_session()
        events.record_attempt(journey, session=session)
        try:
            result = super().portal_call(records, method_name, *args, **kwargs)
        except ValidationError:
            events.record(journey, "validation_error", session=session)
            raise
        events.record(journey, "action", session=session)
        return result
