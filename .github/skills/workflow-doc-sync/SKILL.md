---
name: workflow-doc-sync
description: 'Keeps repository documentation aligned with code changes. Use when business behavior, states, ownership, notifications, integrations, or admin workflows change so the right README, workflow, and top-level docs are updated in the same change set.'
argument-hint: 'Describe the behavior change or the modules touched'
user-invocable: true
---

# Workflow Doc Sync

## What This Skill Produces

This skill selects the right documentation files to update for a code change and keeps the repo’s behavioral docs aligned with the implemented system.

Use it when:
- admin or user workflows change
- state transitions, deadlines, or ownership rules change
- integrations or notification rules change
- a new field or model changes how the system is operated
- you want doc updates in the same patch instead of as follow-up work

## Doc Surfaces In This Repo

Top-level docs:
- `README.md`
- `CONTEXT.md`
- `TECHNICAL_NOTE.md`
- `ROADMAP.md`
- `INTEGRATION_CONTRACTS.md`
- `STATE_AND_OWNERSHIP_MATRIX.md`

Workflow specs:
- `_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md`
- `_workflows/WORKFLOW_RESULT_PIPELINE.md`
- `_workflows/WORKFLOW_PUBLIC_PUBLICATION.md`
- `_workflows/WORKFLOW_MATCH_DAY_OPERATIONS.md`
- `_workflows/WORKFLOW_SEASON_REGISTRATION.md`
- `_workflows/WORKFLOW_FINANCIAL_TRACKING.md`
- plus the other files under `_workflows/`

Addon docs:
- `sports_federation_*/README.md`

## Procedure

1. Identify what kind of change happened.
   - workflow behavior
   - model/schema shape
   - portal/public ownership
   - notifications
   - integrations/env behavior
   - roadmap or architecture

2. Update the smallest required doc set.

### Workflow behavior changed

Update:
- the affected addon `README.md`
- the relevant `_workflows/*.md` file

### Data model or architecture changed

Update:
- the addon `README.md`
- `TECHNICAL_NOTE.md`
- `CONTEXT.md` if the concept map changed

### Ownership, access, or state transitions changed

Update:
- the addon `README.md`
- the relevant workflow doc
- `STATE_AND_OWNERSHIP_MATRIX.md`

### Notification triggers or recipients changed

Update:
- the addon `README.md`
- `INTEGRATION_CONTRACTS.md` (notification matrix section)
- any affected workflow doc

### Integration configuration changed

Update:
- the addon `README.md`
- `INTEGRATION_CONTRACTS.md`
- `README.md` or CI docs if setup commands changed

3. Write docs from the operator’s point of view.
   - describe the behavior now, not the implementation history
   - use the real model names only where they clarify the behavior
   - explain prerequisites, states, and deadlines clearly

4. Keep docs consistent with tests.
   - if tests prove a new rule, the docs should say that rule explicitly
   - if docs describe a workflow, tests should not contradict it

5. Keep doc updates in the same change set.
   - do not leave behavioral docs stale after changing code

## Decision Points

### If only implementation details changed

Update the addon `README.md` or `TECHNICAL_NOTE.md`, not every workflow file.

### If the user journey changed

Update the relevant `_workflows/*.md` file even if the data model change is small.

### If the change only affects developer setup or CI

Update `README.md`, `CONTRIBUTING.md`, and `INTEGRATION_CONTRACTS.md` as needed.

### If a doc seems related but not authoritative

Prefer the authoritative workflow file and the owning addon `README.md` first.

## Quality Bar

Finish only when:
- the right docs were updated in the same patch
- state names, deadlines, and prerequisites match the code
- docs do not describe obsolete behavior
- workflow docs remain operator-friendly instead of turning into code dumps

## Example Invocations

- `/workflow-doc-sync I changed participant confirmation and roster deadlines; update the right docs`
- `/workflow-doc-sync sync docs for a portal ownership change affecting roster management`
- `/workflow-doc-sync choose the correct README and workflow files for a new tournament scheduling behavior`