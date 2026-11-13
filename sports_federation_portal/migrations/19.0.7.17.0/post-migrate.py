"""Representative tenures are judged by date, not by a stored flag.

``is_current`` is no longer stored (a stored flag kept granting portal access
after a tenure ended). This drops the obsolete column and brings the stored
portal scopes of users and the effective users of delegations up to date once,
so access that already expired by date ends with this upgrade. An hourly job
(``_cron_refresh_time_based_state``) keeps them current afterwards.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "ALTER TABLE federation_club_representative DROP COLUMN IF EXISTS is_current"
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    stale = env["res.users"]._refresh_portal_scopes()
    env["federation.club.representative"]._cron_refresh_time_based_state()
    _logger.info(
        "Refreshed portal scopes of %s user(s) with ended or new tenures.", len(stale)
    )
