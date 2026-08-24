# Competition Cutover Acceptance Record

Use this record for the `/tournaments` to `/competitions` release candidate. Complete every mandatory field and attach evidence to the release ticket. Do not commit personal data, credentials, database dumps, or unredacted email samples.

## Candidate identity

- Candidate commit SHA:
- Branch or release tag:
- Validation date:
- Release coordinator:
- Fresh-install database identifier:
- Upgrade-source snapshot identifier:
- Upgrade database identifier:
- Odoo version or commit:
- PostgreSQL version:
- Browser and mobile viewport:

## Automated gate evidence

Record the run URL or artifact identifier and result for each gate.

- Repository lint and contracts:
- Fresh installation:
- Restored-database upgrade:
- Competition core suite:
- Portal suite:
- Public-site suite:
- Backup restore drill:
- Runtime route inventory:
- Open critical defects:
- Open high defects:

## Canonical route cutover

1. `GET /competitions` returns the current competition hub.
2. `GET /competitions/archive` returns archived competition editions only.
3. `GET /competitions/<edition-slug>` exposes only a published edition with at least one published division.
4. Format, schedule, match-day, standings, results, and bracket links remain inside the canonical `/competitions` namespace.
5. `GET /tournaments` redirects once to `/competitions`.
6. A legacy tournament detail URL redirects once to the matching edition and preserves the intended division.
7. Legacy schedule, standings, results, teams, and bracket URLs redirect once without a loop.
8. Unpublished editions, divisions, match days, and schedule publications return 404 or remain absent.
9. Versioned feed and calendar contracts retained by policy still return their declared contract version.

Evidence:

- Canonical route screenshots or HTTP transcript:
- Legacy redirect transcript:
- Publication-boundary evidence:
- Feed and calendar contract evidence:

## Full competition lifecycle

### Registration

- Create a competition and season edition.
- Create at least two divisions and registration windows.
- Register teams through the intended backend and portal paths.
- Confirm that cross-club access and duplicate submission are blocked.
- Confirm ownership is edition and division based, not legacy workspace based.

Result and evidence:

### Format and fixtures

- Create a group stage followed by knockout or placement stages.
- Validate graph cycle rejection and source mappings.
- Materialize fixtures twice and confirm no duplicates.
- Confirm every operational match is fixture backed.

Result and evidence:

### Calendar and scheduling

- Create at least two match days, multiple courts, breaks, and slots.
- Run deterministic and weighted-fairness scheduling.
- Review conflicts, rest time, unscheduled fixtures, and repeated execution.
- Confirm stale concurrent planner changes are rejected without overwriting the winning revision.

Result and evidence:

### Approval and publication

- Submit the schedule for approval.
- Confirm the submitter cannot perform an unauthorized approval.
- Publish an approved immutable schedule revision.
- Modify planning data and confirm the live publication does not change silently.

Result and evidence:

### Match-day operations

- Open the published match day.
- Assign officials and confirm availability and overlap checks.
- Start and complete matches through operational commands.
- Confirm operational slot changes do not rewrite the approved publication.

Result and evidence:

### Results and standings

- Submit, verify, and approve results with separate users.
- Confirm an approved result enters official standings once.
- Contest, correct, and reapprove one result.
- Recompute and freeze standings, then progress the next stage.
- Confirm the public competition page reflects the approved outcome and bracket progression.

Result and evidence:

## Portal and public isolation

- Club A cannot read or mutate Club B registrations, rosters, match sheets, duties, or results.
- Anonymous users cannot see unpublished competition data.
- Portal users see only live schedule publications relevant to represented teams.
- Public and portal pages use competition terminology without migration-generation language.

Result and evidence:

## Recovery and upgrade

- Restore the selected pre-cutover snapshot into the isolated upgrade database.
- Run the `upgrade` RC lane and retain the complete log.
- Verify migration warnings, row counts, legacy cleanup, menus, routes, and module states.
- Restart workers during a non-destructive action and confirm no duplicate records.
- Restore the post-publication backup to another database and verify schedules, results, audits, and attachments.
- Rehearse rollback to the documented restore point.

Result and evidence:

## Defect disposition

For every defect record severity, reproducible steps, evidence, owner, target package, and disposition. Critical and high defects are automatic no-go conditions.

- Defect register location:
- Accepted medium defects and rationale:
- Deferred low defects:

## Decision

- Automated gates: PASS / FAIL
- Human acceptance: PASS / FAIL
- Restore and rollback: PASS / FAIL
- Technical owner approval:
- Tournament operations approval:
- Club representative approval:
- Security or governance approval:
- Data or process owner approval:
- Final decision: GO / NO-GO
