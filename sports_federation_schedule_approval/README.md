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
6. **Publish Schedule** creates an immutable publication, links operational
   matches to their exact slots, and makes the publication current for the match
   day.
7. **Publication > Schedule Publications** retains live and superseded evidence.

The command service enforces edition roles, separation of duties, submitted
revision equality, snapshot-digest equality, and schedule revalidation. Buttons
are only orchestration entry points and never duplicate the business rules.

## Tests and contracts

```bash
python ci/check_phases_3_5_contract.py
python ci/check_phase51_schedule_handoff.py
bash ci/run_tests.sh --module sports_federation_schedule_approval
bash ci/run_tests.sh --suite competition_core
```
