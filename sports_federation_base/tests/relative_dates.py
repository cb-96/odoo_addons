"""Dates for test fixtures, relative to the day the tests run.

A fixed date written as "a future match" (say 12 December 2026) turns into a
past match on 13 December 2026, and tests that depended on it start failing
without any code change. Fixtures whose meaning is relative to today ("an
upcoming match", "the current season") use these helpers instead.
``ci/check_test_date_horizon.py`` keeps new fixed near-future dates out.
"""

from datetime import datetime, time, timedelta

from odoo import fields


def day(offset=0):
    """``today + offset`` days, as an ISO date string."""
    return fields.Date.to_string(fields.Date.today() + timedelta(days=offset))


def moment(offset=0, hour=18, minute=0):
    """``today + offset`` days at ``hour:minute`` (UTC), as an ORM datetime string."""
    target = datetime.combine(
        fields.Date.today() + timedelta(days=offset), time(hour, minute)
    )
    return fields.Datetime.to_string(target)


def current_season(length_days=365, started_days_ago=180):
    """``(date_start, date_end)`` of a season that is running today."""
    return day(-started_days_ago), day(length_days - started_days_ago)
