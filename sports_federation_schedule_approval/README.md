# Schedule Approval

This addon owns independent schedule review and immutable schedule publication.
It does not own working assignments, calendar capacity, or match-day execution.

## Operator flow

1. A schedule planner submits a complete schedule from **Schedule Planner**.
2. The addon creates immutable review evidence and opens the pending review.
3. A different assigned schedule approver opens **Schedule Review Queue**.
4. The approver either enters a note and selects **Request Changes**, or selects
   **Approve Schedule**.
5. Approved reviews appear under **Publication > Approved Schedules**.
6. **Publish Schedule** creates any missing operational matches for the assigned
   fixtures through the fixture materializer, creates an immutable publication,
   links matches to their exact slots, and makes the publication current for the
   match day.
7. **Publication > Schedule Publications** retains live and superseded evidence.

The command service enforces edition roles, separation of duties, submitted
revision equality, snapshot-digest equality for schedule facts, and schedule
revalidation. Operational match links are derived and may be materialized at
publication. Buttons are only orchestration entry points and never duplicate
the business rules.
Role assignments remain administrator-managed; the Schedule Approver group
exposes the workflow actions, while a per-edition `schedule_approver` assignment
authorizes the operation. The role check performs a read-only internal lookup,
and approval revalidation performs controlled read-only access to the submitted
calendar and venue data, so approvers do not need CRUD access to those
administrator-managed records. Reviewers may edit the note while a review is
pending; state and audit fields remain command-service-only.

## Tests and contracts

```bash
python ci/check_phases_3_5_contract.py
python ci/check_phase51_schedule_handoff.py
bash ci/run_tests.sh --module sports_federation_schedule_approval
bash ci/run_tests.sh --suite competition_core
```

## 5.1.1 integrity rules

Review evidence is immutable through the model guard. Pending reviewers may edit
only the note; only the approval command service can write decision fields
through a narrowly scoped context. Publications are live,
versioned and replaced per match day, not per edition. Publication confirmation
locks the match day and verifies the expected current publication before
allocating the next version. Replacements require a dedicated reason that is
separate from the review note.
