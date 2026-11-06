"""Evaluate observed mobile match-day acceptance. Empty evidence never passes."""

import argparse
import json
import math
from statistics import median
from pathlib import Path

SCENARIOS = (
    "before_submission",
    "during_submission",
    "after_submission",
    "reload_reconnect",
    "changed_context",
    "duplicate_replay",
    "storage_failure",
    "second_tab",
)
JOURNEYS = ("official_accept_venue", "court_score_submit", "organiser_replace")


def evaluate(data):
    observations = data.get("users", [])
    participants = [row.get("participant") for row in observations]
    distinct = (
        bool(participants)
        and all(participants)
        and len(set(participants)) == len(participants)
    )
    n = len(observations)
    successful = sum(
        row.get("completed") is True and row.get("assisted") is False
        for row in observations
    )
    understood = sum(row.get("save_location_correct") is True for row in observations)
    times = [
        row["score_entry_seconds"]
        for row in observations
        if row.get("completed") is True
        and row.get("assisted") is False
        and isinstance(row.get("score_entry_seconds"), (int, float))
        and math.isfinite(row["score_entry_seconds"])
        and row["score_entry_seconds"] > 0
    ]
    interruptions = data.get("interruptions", {})

    def interruption_pass(name):
        row = interruptions.get(name, {})
        return (
            row.get("executed") is True
            and row.get("lost_acknowledged_saves") == 0
            and row.get("duplicate_submissions") == 0
            and row.get("silent_overwrites") == 0
        )

    keyboard = data.get("keyboard", {})
    mobile = data.get("viewport_360", {})
    gates = {
        "unassisted_completion_90_percent": distinct
        and n >= 10
        and successful / n >= 0.9,
        "save_location_understanding_90_percent": distinct
        and n >= 10
        and understood / n >= 0.9,
        "median_entry_under_60_seconds": len(times) == successful
        and len(times) >= 9
        and median(times) < 60,
        "interruption_integrity": all(interruption_pass(name) for name in SCENARIOS),
        "critical_keyboard_journeys": all(
            keyboard.get(name) is True for name in JOURNEYS
        ),
        "critical_360px_journeys": all(mobile.get(name) is True for name in JOURNEYS),
    }
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "users": n,
        "unassisted_successes": successful,
        "save_location_correct": understood,
        "median_entry_seconds": median(times) if times else None,
        "missing_interruption_scenarios": [
            name
            for name in SCENARIOS
            if not interruptions.get(name, {}).get("executed")
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.observations.read_text()))
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
