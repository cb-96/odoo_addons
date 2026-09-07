# Match-Day Operations

This addon executes the current immutable schedule publication. It never edits
approved publication evidence.

## Operator workflow

- **Match-Day Control** shows readiness and the exact live publication.
- **Open Match Day** validates the publication digest and creates an immutable
  execution session.
- Court status and incidents are changed through command-backed wizards.
- Operational schedule changes support move, delay, postpone and cancel.
- Every deviation requires a reason and records the session, publication, actor,
  old slot and new slot.
- The immutable `published_slot_id` is preserved. Live reality is represented by
  `operational_slot_id` and `operational_status`.
- Normal close requires all matches finished or cancelled and all incidents
  resolved. Forced close requires a reason.

## Validation

```bash
python ci/check_schedule_handoff_contract.py
python ci/check_publication_integrity_contract.py
bash ci/run_tests.sh --module sports_federation_schedule_approval
bash ci/run_tests.sh --module sports_federation_matchday
```

## Restarting unpublished planning

Match-day managers can use **Restart from Scratch** before any schedule review or
publication evidence exists. The action requires a reason and explicit destructive
confirmation, removes mutable schedules and the old match day, then creates and
opens a clean replacement with the same edition, date, venue, and slot defaults.
Direct deletion of a draft match day also removes its draft or change-requested
working schedules first. Published, reviewed, open, and closed match days remain
protected and must use the normal revision or operational correction workflows.

## Deleting closed test data

Federation managers and match-day managers can use **Delete Match Day** on a
closed match day. The confirmation wizard shows the number of schedules,
publications, execution sessions, deviations, and matches affected. Confirming
the deletion permanently removes the match-day planning and execution evidence;
linked match records remain in the competition but are detached from the deleted
publication and calendar slots. The action requires a reason and displays a
final confirmation popup before deletion.

