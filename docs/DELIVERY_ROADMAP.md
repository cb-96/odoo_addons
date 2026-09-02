# Delivery Roadmap

Owner: Federation Platform Team
Last updated: 2026-09-02
Review cadence: Every release

## Purpose

This roadmap turns the stabilized competition architecture into an executable
sequence of release, product, reliability, operations, and usability milestones.
The ownership chain remains unchanged:

`registration → format → calendar → scheduling → schedule approval → match day`

Published schedules remain immutable, role separation remains enforced, and
portal/public access continues through explicit ownership boundaries.

## Release Baseline Qualification

Status: **Implemented, pending execution on the committed candidate**

### Objective

Create one reproducible candidate commit for which static validation, fresh
installation, focused release surfaces, performance qualification, browser
focus tests, and the full standard suite all pass.

### Automation

Run after committing all functional changes:

```bash
scripts/ci/run_release_baseline.sh
```

The script executes:

1. clean-workspace preflight;
2. static and contract validation;
3. fresh installation and standard tests;
4. core qualification;
5. portal qualification;
6. public-site qualification;
7. performance qualification;
8. browser and release-focus qualification;
9. final full standard suite;
10. machine-readable evidence capture per lane.

Evidence is written under `artifacts/release/baseline/` by default. Override this
with `RELEASE_BASELINE_EVIDENCE_DIR` when CI provides a dedicated artifact
directory.

### Exit criteria

- One immutable candidate SHA is recorded in every evidence file.
- Test failures and errors are zero.
- Static, ownership, workflow, migration, publication, and security contracts pass.
- Performance budgets pass.
- Browser lifecycle, finance, and public-site tours pass.
- Local and GitHub release-candidate validation agree on the same commit.
- The worktree is clean before qualification starts.

## Release Candidate and Migration Evidence

Status: **Next**

### Objective

Prove deployment and recovery against a representative pre-refactor database and
matching filestore.

### Deliverables

- production-like database and filestore restore;
- pre-upgrade invariant snapshot;
- reviewed module upgrade;
- post-upgrade invariant comparison;
- role-separated operator pilot;
- backup checksum and restore evidence;
- rollback drill with named owner and trigger;
- archived RC logs and machine-readable evidence.

### Exit criteria

The upgraded copy preserves competition, registration, fixture, schedule,
publication, match-day, result, standings, portal, public, integration, and
attachment invariants. Restore and rollback complete from the recorded backup.

## Simplified Competition Journey

Status: **Planned**

### Objective

Allow a normal league, tournament day, or cup to be configured, scheduled,
approved, and published without exposing the underlying Odoo model structure.

### Deliverables

- template-led competition creation;
- guided Basics, Participants, Format, Calendar, Schedule, Publish journey;
- user-facing Draft, Ready, Live, Finished presentation states;
- visible blockers, responsible role, and next action;
- advanced stage graph, revision, fairness, and shared-day controls separated
  from the normal path;
- task-first club portal.

### Exit criteria

A trained non-developer completes the normal journey without developer mode,
direct model navigation, manual progression mapping, or shell access.

## Operational Job Reliability

Status: **Partially implemented**

### Objective

Generalize the proven standings recompute reliability pattern without moving
domain execution out of its owning addon.

### Deliverables

- bounded retry and backoff;
- stale-running recovery;
- dead-letter/operator-action state;
- correlation IDs and sanitized error evidence;
- idempotent manual retry;
- operator visibility for notification, report, integration, retention, and
  snapshot jobs;
- shared infrastructure only after two proven consumers exist.

### Exit criteria

Operators can identify what failed, whether it will retry, when it will retry,
how many attempts remain, which correlation ID applies, and whether manual retry
is safe.

## Retention Evidence and Recovery Visibility

Status: **Partially implemented**

### Objective

Turn retention execution into auditable operational evidence and surface
recovery readiness in one place.

### Deliverables

- candidate, deleted, skipped, attachment, and failure counts;
- duration, policy window/version, dry-run flag, and correlation ID;
- read-only retention evidence views;
- overdue and repeated-failure alerts;
- release-readiness checks for disabled or stale retention jobs;
- links to restore and rollback evidence.

### Exit criteria

The release owner can prove that each policy ran, used the intended window,
retained unresolved workflow evidence, cleaned matching attachments, and exposed
failures to operators.

## Consolidated Operational Dashboard

Status: **Planned**

### Objective

Aggregate existing release, job, retention, integration, and competition queues
without duplicating their source records or commands.

### Deliverables

- release readiness and last evidence status;
- queued, retrying, dead-letter, and stale job health;
- retention freshness and outcomes;
- failed or partial integration deliveries;
- registration blockers, review backlog, unpublished approved schedules,
  match-day publication gaps, result backlog, and standings failures;
- direct links to owning records.

### Exit criteria

An operator can assess release and live operational health from one dashboard and
navigate directly to the owning workflow for remediation.

## Accessibility and Operator Usability

Status: **Planned**

### Objective

Qualify the guided journey and principal portal/public workflows for keyboard,
mobile, terminology, and accessible error recovery.

### Deliverables

- keyboard-only competition setup acceptance;
- modal focus and focus-restoration checks;
- linked validation summaries;
- non-color status cues and accessible icon labels;
- mobile portal qualification;
- raw internal-state prevention;
- deterministic training sandbox and operator walkthrough.

### Exit criteria

The release pilot is completable by keyboard, principal mobile portal workflows
remain usable, and user-facing terminology consistently describes the simplified
journey rather than internal model states.

## Change Control

Each milestone must ship as focused, test-backed changes with corresponding
workflow, module, technical, and runbook documentation. New abstractions require
multiple proven consumers. Security checks, ownership boundaries, publication
immutability, and release validation must not be weakened to accommodate
implementation drift.
