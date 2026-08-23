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
python ci/check_phase51_schedule_handoff.py
python ci/check_phases_511_53_contract.py
bash ci/run_tests.sh --module sports_federation_schedule_approval
bash ci/run_tests.sh --module sports_federation_matchday
```
