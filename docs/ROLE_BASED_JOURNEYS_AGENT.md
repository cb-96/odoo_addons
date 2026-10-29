# Agent implementation brief: complete role-based journeys

## Objective

Implement roadmap workstream "Complete role-based journeys" in the ACTUAL checkout.
Deliver working organiser, club representative, team manager, official and reviewer
journeys, backed by shared task projections and source-owned commands. Do not stop at
analysis or another dashboard mockup: implement, test and provide a patch/commit.

The operator reports executing release-confidence work. Verify whether that means the
full passing gate or only its installation command; inspect evidence without assuming a
pass. Do not discard its changes. The supplied bundle still identifies commit
7667e752e90395f72cce82a11af8226d204b1950 on workflow-improvement and does not prove the
post-execution checkout. This brief uses it as a discovery baseline, not authority to
replace current files. Re-read current source and preserve all existing changes.

## Scope and non-goals

In scope: task consistency, role-aware destinations, owner/deadline/next-step presentation,
missing-prerequisite fixes, handoffs, return navigation, status refresh, no duplicate data
entry, focused role entry points, browser tests and novice validation.

Do not implement a new scheduling solver, full officials coverage board, court scoring
application, payment gateway, family identity subsystem, chat or offline sync. Those are
later workstreams. Connect existing official/consent actions now. If an official or reviewer
role is unsupported, document the precise gap and implement the smallest safe journey using
existing roles. Never grant federation-manager access simply to make a portal journey work.

## Existing source: inspect before changing

The uploaded baseline contains:

- `sports_federation_portal/models/operation_task.py`: shared operational tasks, source keys,
  sync, assignment, acknowledgement, digests, source actions and waiting/bucket computation.
- `sports_federation_portal/controllers/operation_tasks.py`: base work inbox controller.
- `sports_federation_portal/controllers/qol.py`: INHERITED active inbox implementation;
  do not patch only the base method or introduce a competing route.
- `sports_federation_portal/controllers/manager_operation_tasks.py`: manager queue.
- `sports_federation_portal/models/competition_queries.py`: scoped competition/workspace data.
- `sports_federation_setup_flow/models/competition_planner.py`: planner counts and destinations.
- `sports_federation_portal/views/portal_templates.xml`: work inbox, task cards and milestones.
- Portal competition, roster, match, result, officiating and parental-approval controllers.
- `sports_federation_portal/tests/test_operation_tasks.py`, `test_qol.py`,
  `test_competition_portal.py`, `test_production_security_matrix.py`, ownership and HTTP tests.
- `sports_federation_demo/tests/test_operator_role_acceptance.py` and browser lifecycle tests.

Reconcile earlier usability-patch changes such as preparation pages, creation drafts,
lineup fixes and focused result screens. Do not duplicate them or reapply old patches.

## Findings to verify in the actual checkout

1. Base action-items controller derives a percentage from `4 - number_of_task_types`.
   This is not authoritative completion, and the QoL override has a different data contract.
   Trace actual route/template ownership; remove any remaining invented progress measure.
2. `_compute_qol_status` derives waiting_on only from task audience. The audience that sees
   a task is not necessarily the actor who can resolve it. A club may be waiting on review.
3. `_task_spec` routes competition entries to a general list; other task types use exact
   records. Use exact entry details or an exact backend record appropriate to the role.
4. Roster task sync queries existing unready rosters. Missing rosters need a task based on
   the registration/participant source, not an impossible missing-roster ID.
5. `_portal_club_ids` uses representative user_id without an is_current filter. Compare it
   with effective_user_id, portal_club_scope_ids and portal_team_scope_ids before changing.
6. `_sync_specs` uses global source-key lookup and writes on refresh. Preserve cross-audience
   idempotency, assignment and audit history; test concurrency and stale-scope completion.
7. Manager queue uses elevated global task reads. Confirm its intended role scope and whether
   planner, reviewer and match-day roles should see narrower work, not all manager records.
8. Task URLs are portal-oriented even for manager/reviewer audiences. Test actual destination
   access rather than assuming a link that exists is usable by the actor.
9. `action_open_source` and direct task/source requests must recheck current access. A task
   record, old URL or assignment is not a permanent authorisation grant.
10. Digests operate on open tasks. Completed tasks and role handoffs must update reminders;
    waiting for federation review must not repeatedly ask a club to perform an unavailable action.

These are baseline review targets, not claims that all defects remain after earlier work.

## Implementation order

### Shared journey/task contract

Reuse `federation.operation.task` and existing query services. Do not create another persisted
queue or a second source of readiness truth. Establish one shared projection contract:

- Stable source identity, task kind and audience.
- Current actor/required role and optional assigned person.
- Club, team, season and edition scope where relevant.
- State: actionable, waiting, completed, unavailable/not checked, or not applicable.
- Blocker reason, exact next action, authoritative deadline (or explicitly none).
- Exact role-appropriate destination and allowlisted return context.
- Check timestamp and completion reason.

Prefer a small read-model adapter over a broad model rewrite. Keep the existing task lifecycle
if adequate; add presentation state separately where audience and actionable state differ.
An acknowledgement is not completion. Only authoritative source transitions complete tasks.
A reopened/corrected source reopens appropriate work without duplicating its identity.

All counts and action destinations must derive from the same scoped identities. Distinguish
team-count, match-day-count and match-count labels. A caller denied a check receives "not
checked for your role", not zero blockers and green readiness. Do not complete tasks merely
because a filtered query or a failed check did not return their source.

### Missing prerequisites and state handoffs

- Missing roster: derive work from a confirmed registration or current participant snapshot;
  clicking creates/reuses the correct team/season/competition roster through existing commands.
  Page refresh and count computation must not create rosters. Repeated clicks are idempotent.
- Draft roster: open its detail with eligibility feedback and activation action if authorised.
- Missing lineup: route to preparation for the relevant day/team. If roster is missing, fix it
  first with an explicit return path. Submitted sheets open review; approved/locked sheets
  are not unfinished. Ignore cancelled fixtures and superseded publications.
- Consent: identify the affected player and participation context. Club uploads, federation
  verifies. Submitted documents show waiting, rejection shows feedback and correction action,
  expiry/revocation reopens work. Do not expose guardian documents beyond current permissions.
- Registration: separate season enrolment and competition entry. Submitted entries wait for
  review; rejected entries return to correction; confirmed entries lead to preparation.
- Results: simple policy and independent review remain distinct. Corrected/contested results
  reopen the proper actor's task. The same role must not acquire approval rights from the UI.
- Officials: connect existing assignment response and club nomination. Acceptance does not
  imply eligibility or attendance. Decline/withdrawal transfers responsibility visibly.

### Role entry points

Use existing menus/routes and add minimal focused entry points only where necessary.
Multi-role users must be able to switch context without new accounts or widened permissions.

Organiser: one next planning action, blockers by division/day, review handoff and return to
same edition. Do not expose technical version/structure fields in ordinary flows.

Club representative: existing work inbox and preparation workspace; own club work, waiting
on federation, delegated work and recently completed. Team/season/edition filters persist.
Unassigned work is visibly unassigned, not silently "mine". Existing assignment rights apply.

Team manager: team-scoped roster/lineup work using existing role/team scope. If the current
role cannot act, show the responsible club representative rather than broadening access.

Official: own assignment list, exact detail, accept/decline and next responsible actor.
Keep club-duty nomination and individual assignment concepts distinct.

Reviewer: only authorised pending decisions, exact source, relevant validation and decision
feedback. Preserve required independent review. Do not show unrelated private club data.

### Safe navigation and refresh

Implement a shared return-context helper rather than ad hoc URL concatenation in every
controller. Preserve role, scope, filters, edition/day/team and originating task where allowed.
Use a fixed set of local route keys plus validated IDs, not arbitrary redirect URLs. Reject
absolute URLs, scheme-relative URLs, backslash variants, encoded traversal and forged IDs.
Every destination rechecks ownership and role; return context cannot confer permission.

Propagate context through forms, POST errors, success redirects, wizard actions and back links.
After mutation, refresh source-owned task projections before rendering counts. If a task was
resolved meanwhile, show "already resolved" and return to the same scoped workspace. Avoid
refresh loops, duplicate routes and repeated expensive global sync calls. Use bounded queries,
pagination and existing query budgets. Do not leak counts from inaccessible scopes.

### Consistent presentation

Each task card answers: What is needed? Why? Who acts next? By when? What happens after this?
Use source-based statuses and clear labels. No fabricated percentages. If displaying progress,
compute it per explicit journey scope with a known denominator and not-applicable checks.
Show unavailable checks separately. Do not use red blockers for informational future work.
Do not show a primary action a user cannot perform; show a waiting handoff instead.

## Tests and evidence

Implement the acceptance checks in `ci/role_journeys/acceptance.json`: five role journeys,
39 automated outcome checks in total, plus real novice observations. Keep test IDs stable.

For each check, record fixture, actor, action, expected state, negative case and source command.
Reuse model tests for invariants, HttpCase for actual HTTP/RPC permissions and browser tours
for navigation, filters, refresh, form errors and mobile/keyboard interaction. Do not use admin
for ordinary role journeys. Include two clubs, two teams, multi-role account, expired
representation, team-only scope and both simple/controlled policy. Add independent database
connections for concurrent task refresh. Mocked controller tests alone are insufficient.

Critical assertions:
- One task identity across repeated refreshes and role handoffs; no stale audience closes
  another audience's valid task. Assignment persists when source presentation changes.
- Count matches exact pending identities and exact action destination scope.
- Missing records are counted without creating them during projection.
- Submitted/approved/locked/cancelled states produce the correct actor and action.
- Forged task/source/return context cannot reveal or mutate another club's records.
- Failed POST keeps form data and return scope; success returns and refreshes counts.
- Acknowledgement does not unblock readiness; resolved task no longer sends reminders.
- Source correction/revocation reopens appropriate work with current feedback.
- All entry points work at small viewport and with keyboard navigation/error focus.

Register tests and browser assets, select them explicitly in CI and reject skipped/zero-test
runs. Add test case maps to the existing release-confidence machinery where relevant. Do not
replace its existing gates. Commit all implementation and tests, then rerun release confidence
for the NEW final candidate. A prior passing commit does not certify these changes.

## Novice acceptance

Prepare five task scripts without naming menus: publish a competition; register/prepare a
club; prepare a team lineup; respond to an official assignment; review a submitted record.
Use at least five novice participants per task. The same five can perform all tasks with
separate role accounts; report role/task-specific results. Use synthetic staging data only.

Record pseudonymous participant code, task, completion, elapsed time, facilitator interventions,
critical incidents and confusing labels. At least 80% per task must complete without
intervention, with no access/approval/data-loss incident. Re-test after fixes.

The agent may prepare scripts and analyse real observations. It must NOT invent participants,
observations or completion rates. If no facilitator/participants are available, deliver code
and automated results with status "awaiting novice validation"; step 2 remains incomplete.

## Evidence format and verifier

Create an external private `journey-execution.json` AFTER actual test execution. It contains
final commit, status, SHA-256 of the acceptance specification, per-check executed test IDs,
exit codes, nonzero test counts and relative artifact paths/checksums. Use keys such as
`organiser.return_to_same_competition` and `shared.return_target_is_local_allowlisted`.
A single test may cover multiple checks only if it asserts every mapped outcome.

Example shape (values below are placeholders, NOT passing evidence):

```json
{
  "commit": "FINAL_CANDIDATE_SHA",
  "status": "passed",
  "spec_sha256": "SHA256_OF_ACCEPTANCE_JSON",
  "checks": {
    "organiser.return_to_same_competition": {
      "status": "passed",
      "test_id": "ActualHttpCase.test_actual_return_navigation",
      "tests_executed": 1,
      "exit_code": 0,
      "evidence": [{"path": "logs/actual-browser.log", "sha256": "ACTUAL_LOG_SHA256"}]
    }
  },
  "novice_observations": []
}
```

Include ALL required keys and real observations, not only the example. Retain raw logs,
screenshots/traces and facilitator records privately. The verifier validates coverage and
integrity, not assertion quality or independent authenticity. Have a human review mappings.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_role_journey_gate.py -v
python ci/verify_role_journeys.py \
  --evidence-dir /private/journey-evidence/final-candidate \
  --release-confidence /private/release-evidence/final-candidate/release-confidence.json
```

Before final sign-off, rerun `ci/release_confidence.py verify` on that release-evidence
directory; the journey verifier checks the summary, not the entire underlying release chain.
Missing evidence is BLOCKED. Never copy unit-test synthetic observations into release evidence.

## Deliverables and completion rule

1. Working code changes in the actual checkout, no duplicate task system or route ownership.
2. Role journey map and source/permission ownership map.
3. Patch/commit, migration notes if fields change, and upgrade instructions.
4. Actual automated results, exact commands and per-check test mappings.
5. Real novice observations or explicit "awaiting novice validation" status.
6. Fresh passing release confidence for the final candidate.
7. Remaining limits and proposed next workstream, without implementing later scope.

Do not report step 2 complete until code, automated tests, novice gate and refreshed release
confidence pass. Never deploy as part of this task. Suggested commit title:
`feat: connect role-based federation journeys through shared operational tasks`.
