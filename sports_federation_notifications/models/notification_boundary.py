"""Isolate notification producers, never the authoritative business command."""

from functools import wraps


def notification_effect(fallback_model="federation.notification.log"):
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            source = args[0] if args and hasattr(args[0], "_name") else None
            return self.env["federation.notification.service"]._run_notification_effect(
                lambda: method(self, *args, **kwargs),
                source=source,
                name=method.__name__,
                fallback_model=fallback_model,
            )

        return wrapped

    return decorate
