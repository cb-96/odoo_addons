# Role journeys acceptance

Owner: Federation Portal and Public Experience
Last reviewed: 2026-11-06
Review cadence: Every release

Acceptance gate for the role-based journeys in `sports_federation_portal`:
organiser, club representative, team manager, official and reviewer. The
behaviour is described in the
[portal README](../../../sports_federation_portal/README.md#role-workspaces-and-scoped-handoffs);
the scenario-by-scenario validation steps are in the
[duty coverage and restored-database suite](duty-coverage.md#role-journey-validation).

## Behaviour under test

- The portal overview (`/my`) is the single entry: the club first, then one
  section each for official assignments, competition planning, result review
  and the federation work queue, shown only for roles the account has. It
  links to the existing workflow owners; there is no second task or approval
  system. Old `/my/work` URLs redirect permanently.
- `/my/result-reviews` lists submitted and verified results under the user's own
  ORM permissions, filtered by the edition's self-review policy.
- Club tasks are bucketed into actionable, waiting, completed and unavailable,
  with an explicit status and next owner. Entry tasks open the exact entry.
- Missing rosters become tasks sourced from confirmed season registrations.
  Viewing does not create rosters; the action opens an explanation and the
  CSRF-protected roster-creation form.
- Team-scoped representatives see and assign work only for their team;
  forged cross-team assignments are rejected at the command boundary.
- Opening a task's source rechecks task and source read access for the viewer.
- Return navigation restores inbox filters after detail pages, form errors
  and POST redirects. It stores no form data, expires after two hours and
  rejects external or encoded return paths.

## Contract and tooling

| File | Purpose |
| --- | --- |
| `ci/role_journeys/acceptance.json` | Five role journeys, automated outcome checks with a partial mapping to tests, and five novice tasks with an 80% unassisted-completion gate |
| `ci/verify_role_journeys.py` | Validates per-check evidence, artifact checksums, the final commit, novice observations and a fresh release-confidence summary for the same candidate |
| `ci/test_role_journey_gate.py` | Unit tests of the gate itself (evidence format only, not product evidence) |

Run the gate's own tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_role_journey_gate.py -v
```

Run the Odoo tests on an isolated staging database:

```sh
odoo -c /path/to/staging.conf -d STAGING_DATABASE \
  --test-enable --test-tags sf_role_journeys --stop-after-init
```

## Remaining gates

The automated test mapping is intentionally partial. The gate stays blocked
until, for the final candidate:

1. the upgrade and full installation lanes pass on authorised staging;
2. real browser runs cover complete role journeys, return navigation, errors,
   mobile, keyboard and account switching;
3. five real novice sessions per task pass the 80% gate, recorded in
   `journey-execution.json`;
4. concurrent task refresh is validated with separate database connections;
5. task synchronization and inbox query budgets are measured at realistic
   volume;
6. release confidence is rerun for the final commit (a summary from an earlier
   commit is not reused).

Open business question: whether tournament-specific reviewer assignments are
needed beyond the current role groups and edition-level independent-review
rules.
