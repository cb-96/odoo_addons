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
        return pytz.timezone(timezone or 'UTC').localize(
            local, is_dst=None).astimezone(pytz.UTC).replace(tzinfo=None)
    except (ValueError, TypeError, pytz.UnknownTimeZoneError,
            pytz.AmbiguousTimeError, pytz.NonExistentTimeError) as exc:
        raise ValueError("Choose a valid, unambiguous time in the event timezone.") from exc
