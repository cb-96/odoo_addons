"""Close roster and missing-roster tasks of competitions already archived."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    scope = env["federation.portal.archive.scope"]
    closed = scope.close_tasks_for_divisions(scope.hidden_division_ids())
    _logger.info("Closed %s task(s) of archived competitions.", closed)
