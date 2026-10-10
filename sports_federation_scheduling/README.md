# Sports Federation Scheduling

The scheduling addon owns working schedules, fixture assignments, schedule
changes, and the weighted fairness auto-schedule preview.

The auto-schedule wizard previews deterministic assignments after applying hard
constraints and weighted fairness penalties. Applying a proposal records the
automatic assignments and schedule changes while checking the schedule revision
for concurrent edits.

All access-control rows, including the auto-schedule wizard permissions, are
loaded through `security/ir.model.access.csv`.

The complete competition schedule wizard uses explicit short Many2many relation
table names for its selected game days and structures. This keeps PostgreSQL
identifiers below its 63-character limit during module installation and upgrade.


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

## Club-aware automatic scheduling

Automatic scheduling treats simultaneous matches involving different teams of
the same club as the first fairness priority. It detects any overlapping slot
windows, not only slots with identical boundaries. After deterministic greedy
construction, a bounded pairwise-swap improvement pass repairs avoidable club
clashes while preserving all hard constraints and pinned manual or operational
assignments. Remaining club clashes therefore indicate constrained capacity or
pinned assignments rather than an avoidable greedy choice.

## Competition-wide schedule consolidation

The competition wizard is the single planning entry point after participants and game days are defined. It generates missing supported structures, evaluates every game day's individual capacity, reports feasibility separately from quality warnings, preserves manual pins, rejects stale previews, and creates draft schedules through the existing fairness solver.

Reruns are explicit: fill missing planning, replace automatic assignments, or rebuild mutable unpublished planning with a reason. Reviewed, published, open, or closed game days are never rebuilt. Result-dependent fixtures remain visible as deferred work.

## Stage- and game-day-scoped generation

The competition schedule preview may be limited to selected competition stages and game days. It reports included and excluded fixtures, shows the proposed allocation and remaining capacity for every selected shared day, warns when multiple stages are mixed, and blocks application when selected fixtures exceed capacity. Published planning remains immutable; corrections use a replacement amendment after live operations are closed.

## Competition workspace handoff (19.0.3.6.0)

The complete-competition schedule wizard preserves the workspace return context through preview and returns to the same competition planner after apply. The generated schedules, allocations, slots, validation, fairness checks, and protected submission commands are unchanged.
