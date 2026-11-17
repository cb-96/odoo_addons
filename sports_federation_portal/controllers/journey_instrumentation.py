"""Record that a volunteer entered a journey. Never changes what the route returns."""

import logging

from odoo import http
from odoo.http import request

from .connected_journeys import ConnectedPreparation, ConnectedRoleJourneys

_logger = logging.getLogger(__name__)
ENTRY_DEDUPE_SECONDS = 60


def record_entry(journey, screen):
    try:
        request.env["federation.journey.event"].record(
            journey,
            "entry",
            screen=screen,
            session=request.session.sid,
            dedupe_seconds=ENTRY_DEDUPE_SECONDS,
        )
    except Exception:  # pylint: disable=broad-except
        _logger.warning("Journey entry %s was not recorded", journey, exc_info=True)


class InstrumentedRoleJourneys(ConnectedRoleJourneys):
    @http.route()
    def home(self, **kw):
        response = super().home(**kw)
        record_entry("work", "overview")
        return response

    @http.route()
    def open_task(self, task_id, **kw):
        response = super().open_task(task_id, **kw)
        record_entry("task", "task_open")
        return response


class InstrumentedPreparation(ConnectedPreparation):
    @http.route()
    def club_preparation(self, **kw):
        response = super().club_preparation(**kw)
        record_entry("preparation", "club_preparation")
        return response
