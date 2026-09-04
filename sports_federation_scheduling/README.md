# Sports Federation Scheduling

The scheduling addon owns working schedules, fixture assignments, schedule
changes, and the weighted fairness auto-schedule preview.

The auto-schedule wizard previews deterministic assignments after applying hard
constraints and weighted fairness penalties. Applying a proposal records the
automatic assignments and schedule changes while checking the schedule revision
for concurrent edits.

All access-control rows, including the auto-schedule wizard permissions, are
loaded through `security/ir.model.access.csv`.


## Operator handoff to independent review

A planner completes fixture-to-slot assignments in **Schedule Planner** and uses
**Submit for Review**. Blocking validation errors prevent submission. When only
warnings remain, a confirmation dialog requires an explicit justification. The
button delegates to `federation.schedule.commands`; when Schedule Approval is
installed, the approval extension creates the immutable pending review in the
same transaction and opens it directly.

Submitted schedules are immutable. If a reviewer requests changes, the schedule
returns to `changes_requested`, where the planner can edit and submit a new
revision. Planners can use the **Reviews** smart button to inspect the current
handoff and retained history.


## Reversible planning

Draft and change-requested schedules refresh the current calendar fixture pool. Late fixtures appear as unassigned work; stale assignments are flagged and never silently deleted. Pending submissions can be withdrawn, while published corrections use governed replacement revisions.


## Multi-division match days

A working schedule covers the complete physical match day, not only the division structure that originally opened the planner. If another division is allocated to the same match day during a governed revision, **Refresh Calendar Fixtures** exposes those fixtures as unassigned work and auto-scheduling includes them in its proposal. Submission remains blocked until every non-bye fixture from every match-day allocation is assigned.

Publication validates the current match-day fixture pool again. If allocations change after review, publication stops and requires a refreshed, complete schedule and a new review instead of silently publishing an incomplete game day.
