"""Close tasks of competitions that were archived before this version.

Earlier versions kept regenerating them, so they stayed visible in the
portal and in the federation's action queue.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    scope = env["federation.portal.archive.scope"]
    closed = scope.close_tasks_for_divisions(scope.hidden_division_ids())
    _logger.info("Closed %s task(s) of archived competitions.", closed)
