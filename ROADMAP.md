# Sports Federation Platform Roadmap

Last updated: 2026-09-04
Last reviewed: 2026-09-04
Owner: Federation Platform Team
Review cadence: Every release
Release train: 2026.08
Release target: First release candidate

## Product direction

The platform is feature-complete for the first release candidate. Scope is frozen
except for release blockers, security or integrity defects, accessibility
regressions, migration defects, documentation drift, and missing evidence.

## Current priorities

### Candidate qualification

Status: **Automation implemented; execution evidence required**

Run clean install, same-version upgrade, focused suites, performance lanes,
acceptance tours, and the full standard suite on one committed SHA.

### Migration rehearsal

Status: **Automation implemented; approved backup required**

Restore an approved production-like backup, compare invariants, and record the
backup checksum, candidate SHA, timings, and reviewer sign-off.

### Security, recovery, and operations

Status: **Implemented; maintain as release gates**

Preserve role separation, portal ownership, immutable publication replacement,
bounded job retry, retention evidence, recovery visibility, and source-owned
correction workflows.

### Accessibility and documentation

Status: **Implemented; execution and continuous maintenance required**

Qualify keyboard, mobile, accessible recovery, empty states, and real operator
terminology. Keep menus, routes, OpenAPI contracts, workflows, module READMEs,
and release runbooks synchronized with code.

## Approval criteria

A candidate is approvable only when all RC lanes pass on the exact committed
SHA, migration rehearsal passes on an approved backup, no release blocker
remains, documentation matches the product, evidence is complete, and the
release owner records sign-off.

## Deferred expansion

No new format, dashboard, integration, or workflow breadth enters the first
candidate. Product expansion resumes after release feedback is reviewed.
