# Roadmap

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release
Release train: 2026.08
Release target: First release candidate

The single list of current priorities, open gaps and deferred work. Delivered
capabilities are described in the documentation of the system itself, not
here. Keep `Release train` aligned with the [release runbook](operations/release-runbook.md)
(`ci/check_release_train.py`).

## Product direction

The platform is feature-complete for the first release candidate. Scope is
frozen except for release blockers, security or integrity defects,
accessibility regressions, migration defects, documentation drift and missing
evidence. No new format, dashboard, integration or workflow breadth enters the
first candidate; product expansion resumes after release feedback is reviewed.

## Current priorities

### Release Candidate and Migration Evidence

Status: **Automation implemented; execution evidence required**

Produce one reproducible candidate commit for which static validation, fresh
installation, same-version upgrade, focused lanes, performance, browser tours
and the lifecycle lane all pass:

```bash
scripts/ci/run_release_baseline.sh
```

Then prove deployment and recovery against an approved production-like
database and filestore:

```bash
scripts/ci/run_migration_rehearsal.sh \
  --backup-dir /path/to/approved-backup \
  --rollback-owner "Release owner" \
  --rollback-trigger "Invariant comparison or acceptance validation fails" \
  --yes
```

Open blocker: the rehearsal against backup `2026-10-11_114539` reports the
retired competition engine as `to upgrade` with legacy stage progression,
match-slot, schedule-revision and workspace-presence rows. A reviewed,
data-preserving migration and rollback decision is required before a
production-like upgrade can be called clean (see the
[release runbook](operations/release-runbook.md#retiring-the-legacy-competition-engine)).

Exit criteria: one immutable candidate SHA in every evidence file; zero test
failures; all static, ownership, workflow, migration, publication and security
contracts green; performance budgets met; browser lifecycle, finance and
public-site tours green; the upgraded copy preserves competition,
registration, fixture, schedule, publication, match-day, result, standings,
portal, public, integration and attachment invariants; restore and rollback
complete from the recorded backup.

### Runtime and human acceptance

Status: **Suites defined; execution required**

Most recent capabilities have source-level and policy tests only. Their Odoo
ORM/HTTP tests, browser runs, concurrency scenarios and novice sessions still
have to run on staging. The [acceptance suites](release/acceptance/README.md)
list the scenarios and gates for each area: competition lifecycle, role
journeys, duty coverage, communications, mobile match day, visual scheduling,
member lifecycle, workspace UX and platform hardening.

### Security, recovery and operations

Status: **Implemented; maintain as release gates**

Preserve role separation, portal ownership, immutable publication replacement,
bounded job retry, retention evidence, recovery visibility and source-owned
correction workflows. See the [stabilization plan](release/stabilization-plan.md).

### Accessibility and documentation

Status: **Implemented; execution and continuous maintenance required**

Qualify keyboard, mobile, accessible recovery, empty states and operator
terminology. Keep menus, routes, OpenAPI contracts, workflows, module READMEs
and the runbook synchronized with code.

## Known gaps

Open items found in implementation reviews. Each needs an owner and a
decision before it is closed.

| Area | Gap |
| --- | --- |
| Retention | No approved retention period, legal hold or erasure procedure yet for participant inbox receipts and deliveries, member evidence revisions, and exported court recovery evidence ([data retention](reference/data-retention.md#data-without-an-automated-retention-window)). |
| Schedule validation | Referee availability, double-booking, certification and club-duty overlap, and venue opening, court suitability and playing-area constraints are not yet all part of schedule validation; approval and publication should block when required officiating or venue checks fail. Transaction tests are needed before parity with the removed planner is claimed. |
| Member services (optional) | Identity backfill for historical records, licence renewal integration and full lifecycle reporting remain open; historical duplicates are not resolved until the legacy inventory is reviewed. |
| Payments (optional accounting) | Payment-provider configuration, sandbox end-to-end integration, automatic settlement and the full failed/partial/refund/cancellation lifecycle are not runtime-qualified. |
| Communications | External provider delivery receipts and webhooks are not implemented; `sent` means accepted by the outbound mail server. Suspension issuance still uses a direct-email fallback instead of a dedicated template. |
| Mobile match day | No cold-start offline application: reloading while fully offline is not supported. Court editing requires a browser with Web Locks. |
| Performance | The duty coverage board state filter, task synchronization and inbox query budgets need measurement on representative restored volumes. |
| Code cleanup | `federation.standing.action_freeze` still looks up the removed `federation.stage.progression` model (a no-op); progression runs through the stage-table bridge in `sports_federation_format`. Remove the dead branch. |
| Import compatibility | The player `name`, team-name and participant-name import fallbacks passed their target exit date (2026-10-15) without a removal decision ([integration contracts](reference/integration-contracts.md#deprecation-policy)). |

## Deferred

- Swiss pairing, ladders and double elimination formats, until their dynamic
  pairing, challenge, loser-bracket and reset-final semantics can be
  represented completely.
- Live push updates on the match-day operations board (it polls today).
- Journey abandonment and time instrumentation beyond the current journey
  events, and role-specific onboarding guides.

## Approval criteria

A candidate is approvable only when all release-candidate lanes pass on the
exact committed SHA, the migration rehearsal passes on an approved backup, no
release blocker remains, documentation matches the product, evidence is
complete, and the release owner records sign-off under the
[approval policy](release/approval-policy.md).
