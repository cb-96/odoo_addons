"""Calculate acceptance from observed CSV data; missing evidence blocks acceptance."""

import argparse
import csv
import json
import math
from collections import defaultdict
from statistics import median

TASKS = (
    "organiser_setup",
    "club_preparation",
    "review_decision",
    "role_switch",
    "status_comprehension",
)
FIELDS = (
    "participant",
    "task",
    "round",
    "commit",
    "device",
    "completed",
    "assisted",
    "next_action_correct",
    "owner_correct",
    "seconds",
    "wrong_turns",
    "errors",
    "duplicate_entries",
)


def evaluate(rows):
    grouped = defaultdict(list)
    seen = set()
    for row in rows:
        if set(FIELDS) - row.keys():
            raise ValueError("Missing required CSV columns")
        if row["task"] not in TASKS or row["round"] not in ("baseline", "candidate"):
            raise ValueError("Unknown task or round")
        if not row["participant"] or not row["commit"] or not row["device"]:
            raise ValueError("Participant, commit and device are required")
        key = (row["participant"], row["task"], row["round"])
        if key in seen:
            raise ValueError("Duplicate participant/task/round observation")
        seen.add(key)
        item = dict(row)
        for field in ("completed", "assisted", "next_action_correct", "owner_correct"):
            if row[field] not in ("0", "1"):
                raise ValueError("%s must be 0 or 1" % field)
            item[field] = int(row[field])
        item["seconds"] = float(row["seconds"])
        if not math.isfinite(item["seconds"]) or item["seconds"] <= 0:
            raise ValueError("seconds must be finite and positive")
        for field in ("wrong_turns", "errors", "duplicate_entries"):
            item[field] = int(row[field])
            if item[field] < 0:
                raise ValueError("Counts must be nonnegative")
        grouped[(row["task"], row["round"])].append(item)
    commits = {row["commit"] for row in rows if row["round"] == "candidate"}
    if len(commits) > 1:
        raise ValueError("Do not combine candidate commits")
    report = {}
    for task in TASKS:
        baseline = grouped[(task, "baseline")]
        candidate = grouped[(task, "candidate")]
        if len(baseline) < 10 or len(candidate) < 10:
            report[task] = {
                "status": "blocked",
                "reason": "At least 10 baseline and 10 candidate observations required",
                "baseline_n": len(baseline),
                "candidate_n": len(candidate),
            }
            continue
        successful = [r for r in candidate if r["completed"] and not r["assisted"]]
        comprehension = sum(
            r["next_action_correct"] and r["owner_correct"] for r in candidate
        )
        baseline_times = [
            r["seconds"] for r in baseline if r["completed"] and not r["assisted"]
        ]
        candidate_times = [r["seconds"] for r in successful]
        improvement = (
            1 - median(candidate_times) / median(baseline_times)
            if candidate_times and baseline_times
            else None
        )
        baseline_errors = sum(r["errors"] for r in baseline) / len(baseline)
        candidate_errors = sum(r["errors"] for r in candidate) / len(candidate)
        wrong_turns = median(r["wrong_turns"] for r in candidate)
        duplicate_entries = sum(r["duplicate_entries"] for r in candidate)
        passed = (
            len(successful) / len(candidate) >= 0.9
            and comprehension / len(candidate) >= 0.9
            and wrong_turns <= 1
            and improvement is not None
            and improvement >= 0.30
            and candidate_errors <= baseline_errors
            and duplicate_entries == 0
        )
        report[task] = {
            "status": "passed" if passed else "failed",
            "candidate_n": len(candidate),
            "unassisted_successes": len(successful),
            "owner_and_action_correct": comprehension,
            "median_wrong_turns": wrong_turns,
            "time_improvement_fraction": improvement,
            "baseline_errors_per_task": baseline_errors,
            "candidate_errors_per_task": candidate_errors,
            "duplicate_entries": duplicate_entries,
        }
    return {
        "status": (
            "passed"
            if all(r["status"] == "passed" for r in report.values())
            else "blocked_or_failed"
        ),
        "candidate_commit": next(iter(commits), None),
        "tasks": report,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.csv_file, newline="", encoding="utf-8") as handle:
        report = evaluate(list(csv.DictReader(handle)))
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
