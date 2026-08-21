# Sports Federation Result Control

Version: 19.0.1.2.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release

Controlled result lifecycle, audit history, separation of duties, and standings officiality for federation matches.

## Workflow

The result path supports draft, submission, verification, approval, contest, and correction as implemented by the match result controls. Approved results are protected against uncontrolled mutation.

## Safeguards

- submit, verify, and approve permissions are checked at action time
- separation-of-duties rules prevent forbidden actor reuse
- approved-score changes require the correction workflow
- audit rows retain actor, action, and before/after context
- standings only consume results that meet the officiality rules
- contested and corrected paths remain traceable

## Integration

Portal and tournament-operation actions call the same model-owned result methods as backend flows. Standings recomputation follows successful official result transitions.

## Tests

Coverage includes lifecycle transitions, immutability, duty separation, contest/correction recovery, audit records, and end-to-end result pipeline tours.

## Removed document

`ROADMAP_RC.md` is deleted. Approved-result immutability is an implemented invariant and belongs in this README and its regression tests, not a permanent mini-roadmap.
