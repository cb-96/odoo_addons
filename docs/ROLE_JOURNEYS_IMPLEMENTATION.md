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
  permissions. Links open existing backend records; existing result commands enforce policy.
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
Two CI helper test files accompany the application tests.

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

## Validation performed here

- 12 Python pure-helper tests passed.
- 12 frontend helper tests passed using a small DOM/storage stub.
- Python/XML parse and JavaScript syntax checks passed.
- Scoped XPath selectors checked against the uploaded inbox template.
- Existing addon integrity, dependency drift, ACL CSV, portal sudo guard and route-ownership
  checks passed. These are static checks, not proof of live permissions or rendering.
- 13 Odoo model/HTTP regression tests written and registered, but NOT executed here.
- No Docker executable or Odoo runtime was available. No deployment or database was changed.

## Remaining acceptance work and known limits

- Execute the model/HTTP tests and full installation/upgrade lanes on staging. Upstream
  portal-home template inheritance and Odoo record URLs require live rendering validation.
- Run real browser tests for complete role journeys, return navigation, errors, mobile,
  keyboard and account switching. Frontend helper tests are not a substitute.
- Run real novice sessions and the previous role-journey evidence gate. No observations
  or completion rates were generated here; not all 39 acceptance checks are certified.
- Validate concurrent refresh with separate database connections. The existing unique
  source-key constraint remains; this patch does not claim to eliminate every create race.
- Review the group-based reviewer list against tournament-specific assignments. Records
  are readable candidates; final verification/approval remains checked by source commands.
- Return navigation covers portal pages. Backend record navigation is native, not a custom
  persisted return to a portal reviewer/manager filter.
- The existing broad task sync and inbox query budgets need runtime performance measurement.
  Waiting entry/reviewer sections explicitly cap their display at 100 records.
- Team projections are populated by sync; old team-only tasks are safely hidden until their
  source is refreshed. Test upgrade behavior for installations with historical task records.
- The existing representation scope computation and midnight tenure refresh are not rewritten.
  Test delegation/expiry in the installation's actual role configuration.

Step 2 is complete only after implementation, runtime/browser checks, real novice validation
and fresh release confidence pass. This deliverable supplies the code, not an agent writing task.

Suggested commit title:
`feat: connect role-based workspaces and operational task handoffs`
