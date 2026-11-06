"""Pure, bounded input validation shared by online and offline commands."""
import hashlib
import json

OUTCOMES = {"normal", "interrupted", "abandoned", "forfeit_home", "forfeit_away", "disputed"}
MODES = {"aggregate", "periods", "sets"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def validate_capture(value, mode="aggregate", set_target=0, max_periods=100, complete=True):
    if not isinstance(value, dict) or set(value) - {
        "home", "away", "periods", "outcome", "reason", "zero_confirmed"
    }:
        raise ValueError("Unknown result fields.")
    if mode not in MODES:
        raise ValueError("Unknown scoring mode.")
    result = {"home": value.get("home", 0), "away": value.get("away", 0),
              "periods": value.get("periods", []), "outcome": value.get("outcome", "normal"),
              "reason": value.get("reason", ""), "zero_confirmed": value.get("zero_confirmed", False)}
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
        if any(type(period[k]) is not int or not 0 <= period[k] <= 100000 for k in ("home", "away")):
            raise ValueError("Invalid period score.")
    if mode == "aggregate" and periods:
        raise ValueError("This competition uses aggregate scoring.")
    if complete and mode in {"periods", "sets"} and result["outcome"] == "normal" and not periods:
        raise ValueError("Enter the sets or periods.")
    if periods:
        totals = (sum(p["home"] for p in periods), sum(p["away"] for p in periods))
        if mode == "sets":
            if complete and any(p["home"] == p["away"] for p in periods):
                raise ValueError("A completed set cannot be tied.")
            totals = (sum(p["home"] > p["away"] for p in periods),
                      sum(p["away"] > p["home"] for p in periods))
            if complete and set_target and result["outcome"] == "normal" and max(totals) != set_target:
                raise ValueError("The winning set target has not been reached.")
            if set_target:
                wins = [0, 0]
                for index, p in enumerate(periods):
                    wins[0 if p["home"] > p["away"] else 1] += 1
                    if max(wins) >= set_target and index != len(periods) - 1:
                        raise ValueError("No sets may follow the winning set.")
        if totals != (result["home"], result["away"]):
            raise ValueError("Aggregate scores do not match periods or sets.")
    if complete and result["outcome"] == "forfeit_home" and result["home"] >= result["away"]:
        raise ValueError("Home forfeit requires an away winning result.")
    if complete and result["outcome"] == "forfeit_away" and result["away"] >= result["home"]:
        raise ValueError("Away forfeit requires a home winning result.")
    return result


def validate_command(command):
    if not isinstance(command, dict) or set(command) != {"key", "revision", "operation", "payload", "signature"}:
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
