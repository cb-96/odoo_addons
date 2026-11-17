# Sports Federation workflow roadmap acceptance

Owner: Federation Competition Operations
Last reviewed: 2026-11-17
Review cadence: Every release candidate

This checklist is the release boundary for the connected workflow roadmap. It
supplements module tests; it does not turn static checks into runtime evidence.
The qualification files currently under `artifacts/qualification/baseline` were
recorded for commit `718f7f8f7f6d83167a6be9a7aa3ab01fe4e60118`. They are useful
historical evidence, but they are **not** exact-current-commit evidence for source
commit `d1d44d91ae91ca2d2fb0df6f97e13564a5759d25` or for patches applied after it.

## Qualification gate

Before deployment, record all of the following against the exact candidate SHA:

1. Full CI, including static, install, upgrade, lifecycle, acceptance and
   performance lanes.
2. Isolated upgrades of every changed addon.
3. Club-duty planning on draft and current published schedules.
4. A restored-database rehearsal with before/after invariants and the candidate
   SHA in the evidence.
5. Browser walkthroughs for organiser, club representative, referee/scorer and
   tournament-manager roles.
6. Prepared-device test: prepare online, disconnect, reload the app, score,
   reconnect and verify exactly one server receipt per command key.

An unavailable lane is recorded as unavailable, never as passed.

## End-to-end acceptance

### Authorised and feasible operations

- Confirmed head and assistant referees and an optional club-nominated scorer
  use their own accounts and can score only authorised matches.
- Scorers cannot approve their own official result; manager approval remains a
  separate transition.
- Replacement, cancellation or changed match circumstances remove stale access.
- Club-duty allocation respects declared simultaneous capacity, qualified roles
  and preparation, rest and travel buffers.
- Manual pins survive recalculation; infeasible pins explain why they failed.
- Workload shows role count and duty minutes.
- Automatic generation, manual moves, allocation previews, submission and
  publication use the same schedule and duty facts.
- Publication checks responsibility-plan feasibility without requiring the
  acceptance that publication itself opens.
- Opening a game day requires staffing, roster, venue and document readiness.
- Starting a match requires current accepted, eligible and present officials and
  a current lineup.

### Safe changes and recovery

- A proposed change lists affected teams, officials, duties, lineups,
  communications and public calendars before application.
- Moving an accepted assignment from 10:00 to 14:00 makes the old acceptance
  stale and requires reconfirmation.
- Referee withdrawal or no-show leaves one current successor, preserves the
  responsible club and retains immutable predecessor evidence.
- A prepared court app survives offline reload, keeps visible unsynchronised
  commands and replays each idempotency key exactly once.
- A result correction previews standings, dependent fixtures, publications and
  finance effects; it cannot silently replace participants in a dependent match
  that has started.

### Lower administrative effort

- Eligibility states distinguish the relevant future match date and identify
  the player whose registration or licence needs remediation.
- Reusing a prior lineup copies declaration fields only; it does not copy
  approval, eligibility or participation evidence.
- Division capacity routes excess eligible entries to a stable waiting list.
- A place is reserved by one expiring offer, accepted or released atomically,
  and cannot be allocated twice or bypass an earlier queued team.
- Returned entries show `Changes requested` and resubmit the same entry rather
  than creating a duplicate.
- Communication evidence keeps queued, outbound-server accepted, failed,
  acknowledged and underlying-action-complete facts separate. Provider delivery
  evidence is used only when a provider connector supplies it.

### Financial and governance closure

- An obligation shows successful, partial, failed, cancelled and refunded
  settlement evidence and a recoverable balance; native accounting remains
  optional.
- Reconciliation has its own reference and actor evidence.
- Appeals record appellant, grounds, deadline, evidence, reviewer, decision and
  explicit effect on the sanction; a case cannot close with an active appeal.
- Season closure exposes unresolved results, duties, discipline and finance.
- Next-season copying creates draft configuration only and never copies
  participants, approvals, matches, results, payments or decisions.

## Baseline before targets

Run:

```bash
python3 ci/roadmap_baseline.py \
  --source-commit d1d44d91ae91ca2d2fb0df6f97e13564a5759d25 \
  --output artifacts/roadmap-baseline.json
```

Repository counts are measurements. Runtime qualification and human-journey
fields intentionally remain `null` until exact-commit evidence exists. Collect
journey data on realistic competitions for:

- completion without assistance;
- time to prepare and publish a game day;
- unresolved staffing and eligibility before opening;
- stale acceptance after changes;
- duplicate duties and result submissions;
- successful offline recovery; and
- open exceptions at season closure.

Set numerical targets only after this first observation set is recorded.

## Deferred scope

The release does not add speculative formats, per-module dashboards,
general-purpose messaging, broader default membership services or advanced
optimisation. Basic staffing capacity and connected recovery remain the priority.
