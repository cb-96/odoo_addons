"""Offline court app: app shell, service worker, device API and portal pages.

The app shell and service worker are public: they contain no data. Every API
request authenticates a device token and then runs as the scorer, through
``federation.court.device.service``. Portal pages need a logged-in user.
"""

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

APP_DIR = Path(__file__).resolve().parents[1] / "static" / "court_app"
STATIC_PREFIX = "/sports_federation_live_workspace/static/court_app/"
# Files the service worker keeps on the phone. The page itself is cached too.
APP_FILES = (
    "app.css",
    "main.js",
    "lib/api.js",
    "lib/journal.js",
    "lib/lock.js",
    "lib/policy.js",
    "lib/store.js",
    "lib/sync.js",
    "icon.svg",
)
MAX_BODY = 512 * 1024
# The app shell. It holds no data, so it can be cached and opened offline.
APP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1f3a5f">
<title>Court scoring</title>
<link rel="manifest" href="/court/manifest.webmanifest">
<link rel="icon" href="{prefix}icon.svg">
<link rel="stylesheet" href="{prefix}app.css">
</head>
<body>
<div id="court-app" data-version="{version}"><main><p>Loading…</p></main></div>
<noscript>The court app needs JavaScript. Use the printed scoresheet.</noscript>
<script type="module" src="{prefix}main.js"></script>
</body>
</html>
"""


def app_version():
    """Content hash of the app files: a new release gives a new service worker."""
    sha = hashlib.sha256()
    for name in APP_FILES + ("sw.js",):
        sha.update(name.encode())
        sha.update((APP_DIR / name).read_bytes())
    return sha.hexdigest()[:16]


class CourtApp(http.Controller):
    # ── App shell ────────────────────────────────────────────────────────
    @http.route(
        "/court/app", type="http", auth="public", methods=["GET"], sitemap=False
    )
    def court_app(self, **kw):
        html = APP_PAGE.format(prefix=STATIC_PREFIX, version=app_version())
        return request.make_response(
            html,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-cache"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
            ],
        )

    @http.route(
        "/court/sw.js", type="http", auth="public", methods=["GET"], sitemap=False
    )
    def court_service_worker(self, **kw):
        source = (APP_DIR / "sw.js").read_text(encoding="utf-8")
        files = ["/court/app"] + [STATIC_PREFIX + name for name in APP_FILES]
        source = source.replace("__VERSION__", app_version()).replace(
            "__FILES__", json.dumps(files)
        )
        return request.make_response(
            source,
            headers=[
                ("Content-Type", "application/javascript; charset=utf-8"),
                ("Service-Worker-Allowed", "/court/"),
                ("Cache-Control", "no-cache"),
            ],
        )

    @http.route(
        "/court/manifest.webmanifest",
        type="http",
        auth="public",
        methods=["GET"],
        sitemap=False,
    )
    def court_manifest(self, **kw):
        manifest = {
            "name": _("Court scoring"),
            "short_name": _("Court"),
            "start_url": "/court/app",
            "scope": "/court/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#1f3a5f",
            "icons": [
                {
                    "src": STATIC_PREFIX + "icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                }
            ],
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[("Content-Type", "application/manifest+json")],
        )

    # ── Device API ───────────────────────────────────────────────────────
    def _json(self, payload, status=200, headers=None):
        return request.make_json_response(
            payload,
            status=status,
            headers=[("Cache-Control", "no-store")] + list(headers or []),
        )

    def _error(self, message, code, status):
        return self._json({"error": str(message), "code": code}, status=status)

    def _limited(self, scope):
        decision = request.env["federation.court.device.service"]._rate_limit(
            scope, request.httprequest.remote_addr
        )
        if decision["allowed"]:
            return None
        return self._json(
            {
                "error": _("Too many requests. Try again shortly."),
                "code": "rate_limited",
            },
            status=429,
            headers=[("Retry-After", str(decision["retry_after"]))],
        )

    def _body(self):
        raw = request.httprequest.get_data(cache=False, as_text=False)
        if len(raw) > MAX_BODY:
            raise ValueError("Request too large.")
        value = json.loads(raw or b"{}")
        if not isinstance(value, dict):
            raise ValueError("Send a JSON object.")
        return value

    def _device(self):
        header = request.httprequest.headers.get("Authorization") or ""
        scheme, _sep, token = header.partition(" ")
        if scheme.lower() != "bearer":
            raise AccessError(_("Device token missing."))
        device = request.env["federation.court.device.service"]._authenticate(
            token.strip()
        )
        # From here on, everything runs as the scorer. The service re-checks
        # the scorer's rights for every match it touches.
        request.update_env(user=device.user_id.id)
        return request.env["federation.court.device.service"], device

    def _device_call(self, scope, handler):
        blocked = self._limited(scope)
        if blocked:
            return blocked
        try:
            body = self._body()
        except ValueError as error:
            return self._error(error, "bad_request", 400)
        try:
            service, device = self._device()
        except AccessError as error:
            return self._error(error, "unauthorized", 401)
        try:
            return self._json(handler(service, device, body))
        except AccessError as error:
            return self._error(error, "forbidden", 403)
        except ValidationError as error:
            match_id = body.get("match_id")
            if match_id:
                service._note_conflict(match_id)
            return self._error(error, "conflict", 409)
        except (KeyError, TypeError, ValueError) as error:
            return self._error(error, "bad_request", 400)

    @http.route(
        "/court/api/activate",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def court_activate(self, **kw):
        blocked = self._limited("court_activate")
        if blocked:
            return blocked
        try:
            body = self._body()
            code = str(body.get("code") or "")
        except ValueError as error:
            return self._error(error, "bad_request", 400)
        service = request.env["federation.court.device.service"]
        try:
            device, token = service._activate(
                code, request.httprequest.headers.get("User-Agent")
            )
        except AccessError as error:
            return self._error(error, "unauthorized", 401)
        return self._json({"token": token, "device_id": device.id})

    @http.route(
        "/court/api/pack",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def court_pack(self, **kw):
        def handler(service, device, body):
            pack = service._pack(device)
            pack["database"] = request.db
            return pack

        return self._device_call("court_pack", handler)

    @http.route(
        "/court/api/sync",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def court_sync(self, **kw):
        return self._device_call(
            "court_sync",
            lambda service, device, body: service._sync(
                device, int(body["match_id"]), body.get("commands")
            ),
        )

    @http.route(
        "/court/api/claim",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def court_claim(self, **kw):
        return self._device_call(
            "court_sync",
            lambda service, device, body: service._claim(device, int(body["match_id"])),
        )

    @http.route(
        "/court/api/forget",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def court_forget(self, **kw):
        return self._device_call(
            "court_sync",
            lambda service, device, body: {"revoked": service._revoke_own(device.id)},
        )

    # ── Portal: my court duties ──────────────────────────────────────────
    def _redirect(self, success=None, error=None):
        query = []
        if success:
            query.append("success=" + quote(str(success)))
        if error:
            query.append("error=" + quote(str(error)))
        return request.redirect(
            "/my/court-duties" + ("?" + "&".join(query) if query else "")
        )

    @http.route(
        "/my/court-duties", type="http", auth="user", website=True, methods=["GET"]
    )
    def court_duties(self, **kw):
        service = request.env["federation.court.device.service"]
        return request.render(
            "sports_federation_live_workspace.court_duties_page",
            {
                "days": service._court_duties(),
                "devices": service._own_devices(),
                "club_matches": service._club_matches(),
                "referee": service._own_referee(),
                "success": kw.get("success"),
                "error": kw.get("error"),
                "page_name": "court_duties",
            },
        )

    @http.route(
        "/my/court-duties/prepare",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def court_prepare(self, matchday_id=None, label=None, **kw):
        try:
            code = request.env["federation.court.device.service"]._prepare_device(
                int(matchday_id or 0),
                label,
                request.httprequest.headers.get("User-Agent"),
            )
        except (AccessError, ValidationError, ValueError) as error:
            return self._redirect(error=error)
        # The code travels in the fragment: never sent to a server or logged.
        return request.redirect("/court/app#code=" + quote(code), local=True)

    @http.route(
        "/my/court-duties/devices/<int:device_id>/revoke",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def court_revoke(self, device_id, **kw):
        try:
            request.env["federation.court.device.service"]._revoke_own(device_id)
        except AccessError as error:
            return self._redirect(error=error)
        return self._redirect(success=_("Phone removed. It can no longer send scores."))

    @http.route(
        "/my/court-duties/pin",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def court_pin(self, pin=None, pin_repeat=None, **kw):
        if (pin or "") != (pin_repeat or ""):
            return self._redirect(error=_("The two PINs are different."))
        try:
            request.env["federation.court.device.service"]._set_own_pin(pin)
        except (AccessError, ValidationError) as error:
            return self._redirect(error=error)
        return self._redirect(success=_("Your confirmation PIN is set."))

    @http.route(
        "/my/court-duties/scorers",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def court_nominate(self, match_id=None, user_id=None, **kw):
        try:
            request.env["federation.court.device.service"]._nominate_scorer(
                int(match_id or 0), int(user_id or 0)
            )
        except (AccessError, ValidationError, ValueError) as error:
            return self._redirect(error=error)
        return self._redirect(success=_("Club scorer added."))

    @http.route(
        "/my/court-duties/scorers/<int:scorer_id>/withdraw",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def court_withdraw(self, scorer_id, **kw):
        try:
            request.env["federation.court.device.service"]._withdraw_scorer(scorer_id)
        except AccessError as error:
            return self._redirect(error=error)
        return self._redirect(success=_("Club scorer withdrawn."))
