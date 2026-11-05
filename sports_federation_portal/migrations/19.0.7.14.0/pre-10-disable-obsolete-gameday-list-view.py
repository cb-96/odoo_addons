"""Disable the obsolete inherited game-day roster list before view updates."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

OBSOLETE_VIEW_XMLIDS = (
    "sports_federation_portal.portal_my_match_sheets_gameday",
    "sports_federation_portal.portal_my_match_sheet_detail_gameday",
    "sports_federation_portal.lineup_draft_recovery",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in OBSOLETE_VIEW_XMLIDS:
        view = env.ref(xmlid, raise_if_not_found=False)
        if view and view.active:
            view.write({"active": False})
            _logger.info("Disabled obsolete portal view %s (%s).", xmlid, view.id)
