# Sports Federation Rules

Version: 19.0.1.2.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release

Competition definitions and reusable rule sets for scoring, tie-breaks, eligibility, and qualification.

## Responsibilities

- competition master definitions
- versioned rule sets
- points rules
- ordered tie-break rules
- eligibility rules
- qualification rules
- season-registration and competition eligibility checks

## Eligibility service

The shared eligibility service validates applicable age, gender, licence, suspension, registration, and rule-set requirements before participant acceptance where configured.

## Versioning rule

A rule set used by historical or active competition records must not be silently reinterpreted. Material rule changes require an explicit new version or controlled copy so previously calculated standings remain explainable.

## Tests

Coverage includes competition configuration, rule-set behavior, eligibility resolution, child rules, ordering, and historical compatibility expectations.

## Removed document

`ROADMAP_RC.md` is deleted. Its remaining concerns, rule-set immutability and regression coverage, are durable invariants documented here and enforced by tests.
