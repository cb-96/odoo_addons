"""Explicit event-local time conversion; stored instants remain UTC."""

from datetime import datetime
import pytz


def local_to_utc(value, timezone):
    if not value:
        return None
    try:
        local = datetime.fromisoformat(value) if isinstance(value, str) else value
        if local.tzinfo is not None:
            raise ValueError("Use a local time without an offset.")
        return (
            pytz.timezone(timezone or "UTC")
            .localize(local, is_dst=None)
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )
    except (
        ValueError,
        TypeError,
        pytz.UnknownTimeZoneError,
        pytz.AmbiguousTimeError,
        pytz.NonExistentTimeError,
    ) as exc:
        raise ValueError(
            "Choose a valid, unambiguous time in the event timezone."
        ) from exc


def utc_to_local(value, timezone="UTC"):
    if not value:
        return None
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    if instant.tzinfo is None:
        instant = pytz.UTC.localize(instant)
    return instant.astimezone(pytz.timezone(timezone or "UTC"))
