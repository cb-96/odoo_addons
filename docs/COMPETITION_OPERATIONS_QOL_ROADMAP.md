# Competition Operations Quality of Life Roadmap

Owner: Federation Competition Operations
Last updated: 2026-09-03
Review cadence: Every release

## Purpose

Reduce clicks, ambiguity, recovery time, and support requests without adding a parallel workflow or another dashboard.

## Implemented contracts

- Operational tasks expose blocker, next step, deadline, responsible club, assignee, urgency bucket, digest status, and direct source navigation.
- Retryable operational jobs can be retried from the task; business recovery remains in the owning workflow so reasons and role separation are preserved.
- Backend and portal actions use state-based visibility and native Odoo favorites for reusable queue filters.
- Registration decisions, reminders, and governed imports provide safe bulk operations; schedule changes remain revision-owned.
- Chatter and tracked activities provide the authoritative timeline without copying events into another model.
- Club work is grouped into action now, due soon, waiting, and recently completed, with daily digest notifications.
- Authenticated cross-module search resolves competitions, tournaments, teams, registration windows, schedules, and matches to typed direct links.
- Existing operational queues and the consolidated dashboard remain the action workbench; no duplicate KPI model is introduced.

## Exit criteria

Users can identify the next action and owner, reach the source in one step, retry failed jobs safely, process supported bulk work, review authoritative history, find records without knowing module boundaries, and work from urgency-based queues.
