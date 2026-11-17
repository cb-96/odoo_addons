"""Pure, bounded input validation shared by online and offline commands."""

import hashlib
import json

OUTCOMES = {
    "normal",
    "interrupted",
    "abandoned",
    "forfeit_home",
    "forfeit_away",
    "disputed",
}
MODES = {"aggregate", "periods", "sets"}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def set_points(period, win_points=1, draw_points=0):
    """Points each team earns for one set (WDBF 10.2-10.3: 2 won, 1 drawn)."""
    if period["home"] == period["away"]:
        return draw_points, draw_points
    if period["home"] > period["away"]:
        return win_points, 0
    return 0, win_points


def validate_capture(
    value,
    mode="aggregate",
    set_target=0,
    max_periods=100,
    complete=True,
    win_points=1,
    draw_points=0,
):
    if not isinstance(value, dict) or set(value) - {
        "home",
        "away",
        "periods",
        "outcome",
        "reason",
        "zero_confirmed",
    }:
        raise ValueError("Unknown result fields.")
    if mode not in MODES:
        raise ValueError("Unknown scoring mode.")
    result = {
        "home": value.get("home", 0),
        "away": value.get("away", 0),
        "periods": value.get("periods", []),
        "outcome": value.get("outcome", "normal"),
        "reason": value.get("reason", ""),
        "zero_confirmed": value.get("zero_confirmed", False),
    }
    if result["outcome"] not in OUTCOMES:
        raise ValueError("Unknown match outcome.")
    if not isinstance(result["reason"], str) or len(result["reason"]) > 2000:
        raise ValueError("Reason must be at most 2000 characters.")
    result["reason"] = result["reason"].strip()
    if result["outcome"] != "normal" and not result["reason"]:
        raise ValueError("Record a reason for exceptional outcomes.")
    if type(result["zero_confirmed"]) is not bool:
        raise ValueError("Zero score confirmation must be a boolean.")
    for key in ("home", "away"):
        if type(result[key]) is not int or not 0 <= result[key] <= 100000:
            raise ValueError("Scores must be non-negative bounded integers.")
    periods = result["periods"]
    if not isinstance(periods, list) or len(periods) > max_periods:
        raise ValueError("Too many periods or invalid period data.")
    for period in periods:
        if not isinstance(period, dict) or set(period) != {"home", "away"}:
            raise ValueError("Each period needs exactly two scores.")
        if any(
            type(period[k]) is not int or not 0 <= period[k] <= 100000
            for k in ("home", "away")
        ):
            raise ValueError("Invalid period score.")
    if mode == "aggregate" and periods:
        raise ValueError("This competition uses aggregate scoring.")
    if (
        complete
        and mode in {"periods", "sets"}
        and result["outcome"] == "normal"
        and not periods
    ):
        raise ValueError("Enter the sets or periods.")
    if periods:
        totals = (sum(p["home"] for p in periods), sum(p["away"] for p in periods))
        if mode == "sets":
            # A set can end in a draw (WDBF rule 10.3). The match score is the
            # sum of set points; with the defaults (1 won, 0 drawn) that is
            # "sets won". The set target always counts won sets.
            points = [set_points(p, win_points, draw_points) for p in periods]
            totals = (sum(p[0] for p in points), sum(p[1] for p in points))
            wins = (
                sum(p["home"] > p["away"] for p in periods),
                sum(p["away"] > p["home"] for p in periods),
            )
            if (
                complete
                and set_target
                and result["outcome"] == "normal"
                and max(wins) != set_target
            ):
                raise ValueError("The winning set target has not been reached.")
            if set_target:
                wins = [0, 0]
                for index, p in enumerate(periods):
                    if p["home"] != p["away"]:
                        wins[0 if p["home"] > p["away"] else 1] += 1
                    if max(wins) >= set_target and index != len(periods) - 1:
                        raise ValueError("No sets may follow the winning set.")
        if totals != (result["home"], result["away"]):
            raise ValueError("Aggregate scores do not match periods or sets.")
    if (
        complete
        and result["outcome"] == "forfeit_home"
        and result["home"] >= result["away"]
    ):
        raise ValueError("Home forfeit requires an away winning result.")
    if (
        complete
        and result["outcome"] == "forfeit_away"
        and result["away"] >= result["home"]
    ):
        raise ValueError("Away forfeit requires a home winning result.")
    return result


def validate_command(command):
    if not isinstance(command, dict) or set(command) != {
        "key",
        "revision",
        "operation",
        "payload",
        "signature",
    }:
        raise ValueError("Malformed court command.")
    if not isinstance(command["key"], str) or not 8 <= len(command["key"]) <= 80:
        raise ValueError("A bounded idempotency key is required.")
    if type(command["revision"]) is not int or command["revision"] < 0:
        raise ValueError("Invalid revision.")
    if command["operation"] not in {"save", "undo", "submit"}:
        raise ValueError("Unknown court command.")
    if not isinstance(command["signature"], str) or len(command["signature"]) != 64:
        raise ValueError("A schedule and result signature is required.")
    return command


# ── Offline device commands ──────────────────────────────────────────────
# Capture commands (save/undo/submit) move the capture revision. Side commands
# record crossed-out players and the match log; they are idempotent by key
# and do not move the revision, so a phone never has to count them.
CAPTURE_OPERATIONS = {"save", "undo", "submit"}
SIDE_OPERATIONS = {"participation", "log"}
LOG_EVENT_TYPES = {
    "card_blue",
    "card_yellow",
    "card_red",
    "team_card_yellow",
    "team_card_red",
    "staff_card_yellow",
    "staff_card_red",
    "timeout",
    "challenge",
}
PLAYER_EVENT_TYPES = {"card_blue", "card_yellow", "card_red"}
MAX_LOG_EVENTS = 300
MAX_SHEETS = 4
MAX_SHEET_PLAYERS = 40


def _bounded_int(value, low, high):
    return type(value) is int and low <= value <= high


def validate_device_command(value):
    """Split a phone command into the court command and its extras.

    Returns ``(command, extra)``. ``extra`` holds the head-referee
    confirmation of a submit; it is never part of the receipt digest, so a
    PIN is not stored with the receipt.
    """
    if not isinstance(value, dict):
        raise ValueError("Malformed court command.")
    operation = value.get("operation")
    if operation in CAPTURE_OPERATIONS:
        if set(value) - {
            "key",
            "revision",
            "operation",
            "payload",
            "signature",
            "confirmation",
        }:
            raise ValueError("Malformed court command.")
        command = {k: v for k, v in value.items() if k != "confirmation"}
        validate_command(command)
        extra = {}
        if "confirmation" in value:
            if operation != "submit":
                raise ValueError("Only a submission can carry a confirmation.")
            extra["confirmation"] = validate_confirmation(value["confirmation"])
        return command, extra
    if operation in SIDE_OPERATIONS:
        if set(value) != {"key", "operation", "payload"}:
            raise ValueError("Malformed court command.")
        if not isinstance(value["key"], str) or not 8 <= len(value["key"]) <= 80:
            raise ValueError("A bounded idempotency key is required.")
        if not isinstance(value["payload"], dict):
            raise ValueError("Malformed court command.")
        return dict(value), {}
    raise ValueError("Unknown court command.")


def validate_confirmation(value):
    if not isinstance(value, dict) or value.get("method") not in {"self", "pin"}:
        raise ValueError("Unknown result confirmation.")
    if value["method"] == "self":
        if set(value) != {"method"}:
            raise ValueError("Unknown result confirmation.")
        return {"method": "self"}
    pin = value.get("pin")
    if set(value) != {"method", "pin"} or not isinstance(pin, str):
        raise ValueError("Enter the head referee's PIN.")
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        raise ValueError("A PIN has 4 to 6 digits.")
    return {"method": "pin", "pin": pin}


def validate_participation(payload):
    """Complete crossed-out list per match sheet: ``{"sheets": {"12": [3, 4]}}``."""
    sheets = payload.get("sheets") if isinstance(payload, dict) else None
    if set(payload or {}) != {"sheets"} or not isinstance(sheets, dict):
        raise ValueError("Send the crossed-out players per line-up.")
    if not 1 <= len(sheets) <= MAX_SHEETS:
        raise ValueError("Too many line-ups in one command.")
    result = {}
    for sheet_id, player_ids in sheets.items():
        try:
            sheet = int(sheet_id)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid line-up.") from error
        if sheet <= 0 or not isinstance(player_ids, list):
            raise ValueError("Invalid line-up.")
        if len(player_ids) > MAX_SHEET_PLAYERS or len(set(player_ids)) != len(
            player_ids
        ):
            raise ValueError("Invalid crossed-out players.")
        if not all(_bounded_int(item, 1, 2**31 - 1) for item in player_ids):
            raise ValueError("Invalid crossed-out players.")
        result[sheet] = sorted(player_ids)
    return result


def validate_match_log(payload):
    """Complete list of cards, time-outs and challenges for the match."""
    events = payload.get("events") if isinstance(payload, dict) else None
    if set(payload or {}) != {"events"} or not isinstance(events, list):
        raise ValueError("Send the match log as a list of events.")
    if len(events) > MAX_LOG_EVENTS:
        raise ValueError("The match log is too long.")
    result = []
    for event in events:
        if not isinstance(event, dict) or set(event) - {
            "type",
            "side",
            "player_id",
            "half",
            "set",
            "note",
        }:
            raise ValueError("Invalid match log event.")
        kind = event.get("type")
        if kind not in LOG_EVENT_TYPES or event.get("side") not in {"home", "away"}:
            raise ValueError("Invalid match log event.")
        player = event.get("player_id")
        if kind in PLAYER_EVENT_TYPES:
            if not _bounded_int(player, 1, 2**31 - 1):
                raise ValueError("A player card needs the player.")
        elif player is not None:
            raise ValueError("Only player cards name a player.")
        half = event.get("half")
        if half is not None and half not in (1, 2):
            raise ValueError("Half must be 1 or 2.")
        set_no = event.get("set")
        if set_no is not None and not _bounded_int(set_no, 1, 100):
            raise ValueError("Invalid set number.")
        note = event.get("note", "")
        if not isinstance(note, str) or len(note) > 200:
            raise ValueError("Notes are limited to 200 characters.")
        result.append(
            {
                "type": kind,
                "side": event["side"],
                "player_id": player,
                "half": half,
                "set": set_no,
                "note": note.strip(),
            }
        )
    return result
