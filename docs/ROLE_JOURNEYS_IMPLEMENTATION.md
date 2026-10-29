# Role-based journeys: implementation patch

## Status

Actual application code is implemented in the existing sports_federation_portal addon.
No new addon, task table, approval bypass or payment integration is introduced.
This replaces the earlier documentation-only handoff as the implementation deliverable.
It is a staging candidate, NOT a declaration that roadmap step 2 has passed all gates.

## Implemented

- `/my/work`: role-aware entry points for club/team preparation, official assignments,
  existing competition planning, manager follow-up and result review.
- `/my/work/reviews`: pending submitted/verified results read under the actual user's ORM
  permissions and filtered through edition-level self-review policy. Links open existing
  backend records; existing result commands enforce policy.
- Existing manager route now renders a working queue template and backend task links.
  Its role/filter checks remain in the original inherited controller.
- Existing club inbox remains the route owner, extended through its QoL controller.
  Waiting and unavailable tasks move to the waiting bucket, with explicit status/next owner.
- Submitted competition entries have a separate read-only waiting section sourced from
  current scoped records, not a second persisted task queue or another club action.
- Entry tasks open exact entry details rather than a generic entry list.
- Missing rosters become tasks sourced from confirmed season registrations. GET/sync does
  not create rosters. The action opens a scoped explanation and existing CSRF-protected
  roster-creation POST. Existing model commands reuse a roster on repeated submission.
- New `journey_team_id` projection and updated record rule support team-only task scope.
  Expired/current representation and effective-account lookup are considered in task scope.
- Team-specific task assignments now accept only representatives for that team or
  whole-club representatives; the command boundary rejects a forged cross-team user ID.
- Source presentation evaluates ownership using the authenticated viewer even when task
  searches are elevated; source records outside that viewer's scope render unavailable.
- The manager queue entry and form use the existing `/federation/operations/action-items`
  route. Official return navigation preserves only an allowlisted assignment filter.
- Task presentation distinguishes actionable, waiting, completed and unavailable source.
  Submitted sheets and submitted draft consent documents wait for federation review.
- Task sync preserves identities and assignment, skips unchanged writes, preserves a
  completed timestamp, and reopens resolved tasks without carrying an old digest date.
  Registration-derived missing-roster cleanup is isolated from the existing broad sync.
- Digest refresh selects only current actionable tasks, not waiting or resolved work.
- Source opening rechecks task and source read access; no raw elevated source action.
- User-scoped session return navigation restores the inbox filters after portal detail,
  form errors and POST redirects. It stores no form/document data, expires after two hours,
  rejects external/encoded return paths and fails safely when storage is unavailable.
- Removed the base controller's invented percentage derived from the number of task types.
- Portal version raised from 19.0.7.4.1 to 19.0.7.5.0; imports, assets, data and tests registered.

## What is reused, not rewritten

The existing competition planner, draft recovery, roster/lineup commands, official response,
parental approval upload/verification and result policy commands remain authoritative.
Backend navigation uses native record navigation. This patch does not add a new solver,
court scoring application, identity subsystem, chat, payment gateway or offline sync.

## Files

New: journey_navigation.py, models/journey_operation_task.py,
controllers/role_journeys.py, views/role_journey_templates.xml,
static/src/js/journey_return_navigation.js and tests/test_role_journeys.py inside portal.

Updated: portal manifest, package imports, operational-task record rule and base inbox
percentage removal. Existing domain models and earlier release scripts are not replaced.
CI helper tests and the partial test-to-acceptance map accompany the application tests.

## Apply and upgrade

Prefer the patch over overwriting existing files, particularly after the release-confidence
work. The patch is based on the uploaded source snapshot. If git apply --check reports a
conflict, do not force it or replace the whole addon: reconcile that file against the current
checkout. The ZIP contains changed files for inspection, not a complete replacement addon.

```sh
git apply --check role_journeys_implementation.patch
git apply role_journeys_implementation.patch
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_role_journey_helpers.py -v
node ci/test_role_journey_navigation.cjs
```

On an isolated staging database, upgrade sports_federation_portal with the existing Odoo
configuration. The new field must exist before the new views/record rule are used.

```sh
odoo -c /path/to/staging.conf -d STAGING_DATABASE \
  -u sports_federation_portal --stop-after-init
odoo -c /path/to/staging.conf -d STAGING_DATABASE \
  --test-enable --test-tags sf_role_journeys --stop-after-init
```

The database/config values are placeholders, not an instruction to use production.
Tests are also tagged sf_release_confidence and are selected by the existing portal/full
release lanes. Rerun release confidence for the final committed candidate after upgrading.
Do not reuse a passing summary from the previous commit.

## Validation performed

- 13 Python helper tests, 16 evidence-gate unit tests, and 14 frontend helper assertions
  passed. The frontend test uses a stub DOM/storage environment, not a real browser.
- JavaScript syntax, addon integrity (29 addons), dependency drift (30 modules), ACL CSV
  integrity (269 records), portal sudo guard, and route ownership (118 routes) passed.
- Focused isolated Odoo portal CI passed: 20 post-tests, 20 passed, 0 failures/errors,
  including six ordinary-role `HttpCase` scenarios and model-level regressions.
- Full isolated `sports_federation_portal` module CI passed: 161 tests, including 61
  post-tests, 0 failures, and 0 errors.
- These automated checks do not certify every acceptance item, actual browser behavior,
  staging upgrade, or novice usability.

## Remaining acceptance work and known limits

- Execute the upgrade and full installation lanes on authorized staging. No staging config,
  approved sanitized fixture, or staging operator credentials were supplied here.
- Run real browser tests for complete role journeys, return navigation, errors, mobile,
  keyboard and account switching. Frontend helper tests are not a substitute.
- Run five real novice sessions per task and the role-journey evidence gate. No observations
  or completion rates were generated; unmapped acceptance checks remain explicitly unproven.
- Validate concurrent refresh with separate database connections. The existing unique
  source-key constraint remains; this patch does not claim to eliminate every create race.
- Confirm whether business policy requires tournament-specific reviewer assignments beyond
  the current role-group and edition-level independent-review rules before staging sign-off.
- Return navigation covers portal pages. Backend record navigation is native, not a custom
  persisted return to a portal reviewer/manager filter.
- The existing broad task sync and inbox query budgets need runtime performance measurement.
  Waiting entry/reviewer sections explicitly cap their display at 100 records.
- Team projections are populated by sync; old team-only tasks are safely hidden until their
  source is refreshed. Test upgrade behavior for installations with historical task records.
- The existing representation scope computation and midnight tenure refresh are not rewritten.
  Test delegation/expiry in the installation's actual role configuration.

Step 2 is incomplete until staging upgrade, real browser/novice validation and fresh release
confidence pass for the final commit. This run did not deploy or touch a staging or production
database. Release confidence remains blocked pending the approved sanitized backup, source and
attachment metadata, rollback owner/trigger, and private evidence inputs identified by the
release gate.

Suggested commit title:
`feat: connect role-based workspaces and operational task handoffs`
