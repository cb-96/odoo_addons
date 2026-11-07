"""Minimal stand-in for the Odoo court endpoints, for browser testing."""
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "sports_federation_live_workspace/static/court_app"
PREFIX = "/sports_federation_live_workspace/static/court_app/"
FILES = ["app.css", "main.js", "lib/api.js", "lib/journal.js", "lib/lock.js", "lib/policy.js", "lib/store.js", "lib/sync.js", "icon.svg"]
src = (ROOT / "sports_federation_live_workspace/controllers/court_app.py").read_text()
PAGE = re.search(r'APP_PAGE = """(.*?)"""', src, re.S).group(1)
VERSION = "v1"
SIG = "a" * 64
STATE = {
    "token": "tok-123", "revision": 0, "log": [], "received": [], "crossed": {}, "result_state": "draft",
    "submitted": False, "confirmation": None, "source": "head_referee", "force_conflict": False,
    "payload": {"home": 0, "away": 0, "periods": [], "outcome": "normal", "reason": "", "zero_confirmed": False},
}


def pack():
    return {
        "device": {"id": 1, "label": "Test phone", "user": "Eva Claeys", "user_id": 2, "expires_at": "2099-01-01 00:00:00"},
        "matchday": {"id": 5, "name": "Game day 3", "date": "2026-11-15", "venue": "Sporthal Bourgoyen", "timezone": "Europe/Brussels"},
        "matches": [{
            "id": 7, "name": "Gent – Antwerp", "home": "Gent Gladiators", "away": "Antwerp Ballistics", "court": "Court 2",
            "start": "2026-11-15 13:30:00", "end": "2026-11-15 14:30:00", "result_state": STATE["result_state"], "source": STATE["source"],
            "head_referee": {"id": 3, "name": "Eva Claeys"}, "officials": [],
            "scoring": {"mode": "sets", "set_target": 0, "set_points": [2, 1], "max_periods": 30},
            "lineups": [
                {"sheet_id": 11, "side": "home", "team": "Gent Gladiators", "state": "approved", "limit": 12,
                 "players": [{"id": i, "name": f"Home player {i}", "number": str(i), "captain": i == 1, "crossed_out": False} for i in range(1, 15)]},
                {"sheet_id": 12, "side": "away", "team": "Antwerp Ballistics", "state": "approved", "limit": 12,
                 "players": [{"id": 100 + i, "name": f"Away player {i}", "number": str(i), "captain": False, "crossed_out": False} for i in range(1, 9)]},
            ],
            "capture": {"revision": STATE["revision"], "payload": STATE["payload"], "match_log": STATE["log"], "submitted": STATE["submitted"],
                        "closed": False, "device_id": 1 if STATE["revision"] else False, "this_device": True},
            "signature": SIG,
        }],
        "log_event_types": [], "database": "db",
        "pack_hash": hashlib.sha256(json.dumps(STATE["payload"]).encode()).hexdigest() + str(STATE["revision"]),
    }


def current():
    return {"match_id": 7, "revision": STATE["revision"], "payload": STATE["payload"], "match_log": STATE["log"], "signature": SIG,
            "submitted": STATE["submitted"], "closed": False, "review_required": False, "result_state": STATE["result_state"],
            "device_id": 1, "this_device": True, "referee_confirmation": False}


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, ctype, extra=()):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/court/app":
            return self.send(200, PAGE.format(prefix=PREFIX, version=VERSION), "text/html; charset=utf-8", [("Cache-Control", "no-cache")])
        if path == "/court/sw.js":
            js = (APP / "sw.js").read_text().replace("__VERSION__", VERSION).replace("__FILES__", json.dumps(["/court/app"] + [PREFIX + f for f in FILES]))
            return self.send(200, js, "application/javascript", [("Service-Worker-Allowed", "/court/"), ("Cache-Control", "no-cache")])
        if path == "/court/manifest.webmanifest":
            return self.send(200, json.dumps({"name": "Court", "start_url": "/court/app", "scope": "/court/", "display": "standalone"}), "application/manifest+json")
        if path.startswith(PREFIX):
            file = APP / path[len(PREFIX):]
            ctype = {"js": "application/javascript", "css": "text/css", "svg": "image/svg+xml"}[file.suffix[1:]]
            return self.send(200, file.read_bytes(), ctype)
        return self.send(404, "not found", "text/plain")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

        def reply(status, value):
            return self.send(status, json.dumps(value), "application/json")

        if self.path == "/court/api/activate":
            if body.get("code") == "abc":
                return reply(200, {"token": STATE["token"], "device_id": 1})
            return reply(401, {"error": "bad code", "code": "unauthorized"})
        if self.headers.get("Authorization", "") != "Bearer " + STATE["token"]:
            return reply(401, {"error": "This phone is no longer prepared.", "code": "unauthorized"})
        if self.path == "/court/api/pack":
            return reply(200, pack())
        if self.path == "/court/api/sync":
            if STATE["force_conflict"]:
                return reply(409, {"error": "Conflict: schedule, result or draft changed. Keep local evidence and reconcile explicitly.", "code": "conflict"})
            keys = []
            for command in body["commands"]:
                STATE["received"].append(command)
                if command["operation"] in ("save", "submit"):
                    if command["revision"] != STATE["revision"] or command["signature"] != SIG:
                        return reply(409, {"error": "Conflict: schedule, result or draft changed.", "code": "conflict"})
                    STATE["payload"] = command["payload"]
                    STATE["revision"] += 1
                    if command["operation"] == "submit":
                        STATE["submitted"] = True
                        STATE["result_state"] = "submitted"
                        STATE["confirmation"] = command.get("confirmation")
                elif command["operation"] == "log":
                    STATE["log"] = command["payload"]["events"]
                elif command["operation"] == "participation":
                    STATE["crossed"] = command["payload"]["sheets"]
                keys.append(command["key"])
            return reply(200, {"acknowledged_keys": keys, "current": current()})
        if self.path == "/court/api/claim":
            return reply(200, current())
        return reply(404, {"error": "no"})
