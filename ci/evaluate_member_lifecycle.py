#!/usr/bin/env python3
"""Evaluate measured member/family acceptance. Missing evidence fails."""

import argparse
import json
from pathlib import Path
from statistics import mean

REQUIRED = (
    "two_dependants",
    "wrong_person_post",
    "stale_document",
    "revoked_session",
    "payer_scope",
    "cross_company",
    "duplicate_matching",
    "concurrent_matching",
    "renewal_replay",
    "concurrent_renewal",
)


def evaluate(data):
    users = data.get("users", [])
    ids = [row.get("participant") for row in users]
    distinct = len(users) >= 10 and all(ids) and len(set(ids)) == len(ids)
    tasks = sum(
        row.get("completed") is True and row.get("assisted") is False for row in users
    )
    understood = sum(
        row.get("membership_vs_eligibility_correct") is True for row in users
    )
    suite = data.get("adversarial", {})
    executed = all(
        type(suite.get(name, {}).get("executed")) is int and suite[name]["executed"] > 0
        for name in REQUIRED
    )

    def zero(field):
        return executed and all(suite[name].get(field) == 0 for name in REQUIRED)

    touches = data.get("routine_renewals", [])
    valid_touches = len(touches) >= 10 and all(
        row.get("baseline_completed") is True
        and row.get("candidate_completed") is True
        and type(row.get("baseline_touches")) is int
        and row["baseline_touches"] > 0
        and type(row.get("candidate_touches")) is int
        and row["candidate_touches"] >= 0
        for row in touches
    )
    reduction = (
        1
        - mean(row["candidate_touches"] for row in touches)
        / mean(row["baseline_touches"] for row in touches)
        if valid_touches
        else None
    )
    gates = {
        "ordinary_tasks_90_percent": distinct and tasks / len(users) >= 0.9,
        "membership_vs_eligibility_90_percent": distinct
        and understood / len(users) >= 0.9,
        "zero_wrong_person_actions": distinct
        and all(row.get("wrong_person_actions") == 0 for row in users)
        and bool(zero("wrong_person_actions")),
        "zero_stale_approvals": bool(zero("stale_approvals")),
        "zero_unauthorised_document_access": bool(zero("unauthorised_document_access")),
        "zero_duplicate_identities": bool(zero("duplicate_identities")),
        "administrative_touches_reduce_50_percent": valid_touches and reduction >= 0.5,
    }
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "administrative_touch_reduction": reduction,
        "note": "No human measurements or runtime qualification are inferred from source-level tests.",
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
