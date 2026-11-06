# Member lifecycle acceptance

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Acceptance scenarios for the optional `sports_federation_member_services`
addon: family workspace, guardian relationships, renewals, member evidence,
identity review and membership changes. The addon summary is in its
[README](../../../sports_federation_member_services/README.md).

## Install and run the automated checks


Use a disposable staging copy with database and filestore backup. From the
repository root:

```bash
python ci/static_checks.py
python ci/check_access_csv_integrity.py
python ci/check_addon_integrity.py
python ci/check_test_discovery.py
python ci/check_module_dependency_drift.py
python ci/check_http_route_ownership.py
python ci/check_audit_acl_integrity.py
python ci/test_member_lifecycle_policy.py
node --check ci/member_lifecycle_browser.mjs
```

Install `sports_federation_member_services` explicitly (it is optional) or
upgrade it. Use your existing Odoo 19 launcher and
configuration; these arguments are the required test scope:

```bash
odoo server -c YOUR_STAGING_CONFIG -d YOUR_STAGING_DB \
  -u sports_federation_member_services --test-enable \
  --test-tags sf_member_services,sf_member_lifecycle --stop-after-init
```

For first installation, replace `-u` with `-i`. Do not substitute a production
configuration. Then run the repository's full installed-addon test lane, including
people, parental approval, portal, rosters, finance and optional native accounting.
Retain actual logs, candidate commit and configuration with the evidence.

The migration archives existing current member-document revisions. It does not
infer identity links, guardian relationships, membership-document links, payment
ownership or approval. Existing draft memberships still need a review note and
configured required documents before activation. Existing identity records are
reviewed individually, not bulk-linked by email.

## Behaviour under test


- A named-person family workspace with membership, licence, payment, sporting
  eligibility, document requirements and the next responsible role.
- One-person focus, person-bound form values, explicit confirmation and server-side
  rejection of mismatched person/membership/document combinations.
- Reviewed identity linking to existing partners; effect preview; source freshness
  checks; immutable identity decision history.
- Duplicate player retirement and canonical identity reference without deleting
  historical players, licences, results or audit records.
- Private rotatable family references; guardian relationship claims; independent
  evidence review; dated verified access and revocation.
- Later-season renewal that reuses a draft and copies requirements once, never
  document bytes, verification or sporting activation.
- Purpose-scoped uploads, retained evidence revisions, exact-revision review and
  stale-snapshot rejection.
- Missing licence request that reuses the player/season record and stays draft.
- Parental-purpose uploads that create a draft in the existing parental-approval
  model. Generic membership verification cannot approve parental consent.
- Federation-reviewed cancellation, reactivation and membership transfer with
  source revision checks and immutable decided requests.

## Ownership and important distinctions


| Action | Member / verified guardian | Club representative | Federation / finance |
| --- | --- | --- | --- |
| Ordinary renewal | Request for authorised person | Request for currently linked own-club player | Review and activate membership |
| Membership evidence | Upload when personal scope permits | No automatic personal-document access | Request and independently review evidence |
| Guardian relationship | Submit requested evidence and private reference | Help contact federation; no automatic guardianship | Independently verify dates and identities; revoke |
| Player identity / duplicate | Cannot self-link or merge | Escalate matching evidence | Preview and decide identity effects |
| Missing licence | Request draft for active membership | Request within current club scope | Existing licence review and activation |
| Sporting eligibility | Read own current blockers | Own roster/competition preparation | Existing rules, safeguarding and approval owners |
| Payment | Own authorised invoice only | Existing club finance scope | Native invoice, settlement, refund and cancellation owners |
| Cancellation / reactivation / membership transfer | Request with reason | Request within current own-club scope | Decide against current source revision |

**Membership transfer is not a player-club or licence transfer.** It retains the
cancelled source membership and creates a destination draft. Federation sporting
staff must separately decide player club, licences and rosters. The interface says
this explicitly. Membership cancellation does not silently cancel licences,
withdraw rosters, refund payments or reverse invoices. Reactivation returns to
membership review, not active status. These distinctions avoid inventing federation
sporting or financial rules.

Payment summaries require an explicitly linked finance event and the optional
native-accounting bridge for invoice data. Invoice access is checked as the current
user and restricted to their commercial invoice partner. Guardian or payer status
alone never grants someone else's invoice or personal-document access. Missing
billing linkage is shown as unavailable, never as paid or zero balance.

Eligibility is evaluated through the existing roster engine for the member's own
club/season lines. With no relevant roster, the summary says not fully checked.
Passing current roster checks is not a promise of eligibility for every competition
or a replacement for match-day approval.

## Identity matching and history


New complete matching scenarios use NFKC-normalised, case-folded, whitespace-folded
first name + last name + exact date of birth. A database unique key protects new
matching records, including concurrent creates. Matching names without a date of
birth are not enough to infer identity. Email is never a matching credential.
Legacy records retain null keys until reviewed or changed; creation also checks
legacy name/date candidates. Do not claim all historical duplicates are resolved
until the actual legacy inventory has been reviewed.

Use **Review identity / resolve duplicate** on the canonical player. Select an
existing partner, optionally the duplicate player, record the evidence reason,
preview effects, inspect them and confirm. The preview includes actual player
identity values, membership revisions, document checksums/revisions and relationship
states. A changed preview is rejected.

Non-overlapping service history moves to the canonical person with original
references recorded in the immutable decision. Duplicate-person delegations are
revoked, never unioned into canonical permissions. Moved evidence is returned for
independent re-review. Player/licence/result records are retained on their original
historical references. The retired duplicate cannot be reactivated or relinked.

Active duplicate login accounts, cross-company history outside reviewer scope and
overlapping membership keys block consolidation. Resolve those conflicts explicitly
with the appropriate owners; nothing is deleted and no account permissions are merged
to make the operation succeed.

## Guardian and document journeys


Federation staff issue/rotate a private family reference on the existing partner.
The guardian submits that reference and only the requested relationship evidence.
A claim exposes no dependant records before verification. A reviewer other than the
submitter inspects evidence, both identities and validity dates, records a reason
and verifies. The resulting relationship is dated and revocable. Payer relationships
never expand personal scope.

Configure a member-document request with the exact person, membership, purpose,
deadline, validity and whether it blocks membership activation. Use parental purpose
only with guardian-required access and a reviewed canonical player link. Uploaded
is not verified. Parental evidence is reviewed in its owning workflow; the summary
also checks its player identity and document checksum.

For generic evidence, **Verify** opens an exact-revision dialog. Download and inspect
the snapshot, tick inspection and confirm. Returning evidence with a reason permits
replacement. Replacement increments revision and clears verification; an older
review dialog cannot approve it. Current and replaced bytes are retained in immutable
reviewer-only revision records. Historical revision access does not become public
or available through generic portal attachment routes.

Every current upload/download/mutation checks current actor scope. Guardian
revocation and mutations serialize on the same person row; membership and request
rows are locked before state decisions. Caught controller errors use savepoints so
partial renewal/evidence mutations are rolled back. Family responses and downloads
are no-store. Already viewed/downloaded information cannot be recalled, but later
requests from an active session must fail after access is revoked.

**Retention qualification:** the evidence archive prevents ordinary editing and
deletion. Before production, have the federation approve an evidence retention
period and set `sports_federation_member_services.evidence_retention_days`
(see [data retention](../../reference/data-retention.md#legal-hold-and-erasure-of-member-evidence)).
On staging, verify legal hold, release, erasure (refused under hold) and that
the scheduled run removes only replaced revisions past the period. Do not enable public attachment links or unreviewed portal ACLs.

## Automated staging browser / concurrency smoke


`ci/member_lifecycle_browser.mjs` uses Playwright and real prepared staging fixtures.
It exercises two-person separation, a forged wrong-person POST, concurrent renewal,
keyboard upload, stale review, concurrent normalised matching and revocation during
an active session. It makes real staging mutations, including retiring access; use
a disposable database and restore it afterwards.

Prepare two distinct dependant partners, active memberships in the same current
club/season, a later open season, current verified guardian relationships and one
requested **generic** document for dependant A. Do not create the next-season
membership beforehand. Use a valid scan-approved PDF/PNG/JPEG evidence file. Provide
this configuration through `SF_FAMILY_FIXTURES` (JSON):

```json
{
  "guardian_login": "YOUR_GUARDIAN_LOGIN",
  "guardian_password": "YOUR_GUARDIAN_PASSWORD",
  "reviewer_login": "YOUR_REVIEWER_LOGIN",
  "reviewer_password": "YOUR_REVIEWER_PASSWORD",
  "person_a": 0,
  "person_b": 0,
  "membership_a": 0,
  "membership_b": 0,
  "next_season": 0,
  "document_a": 0,
  "relationship_a": 0,
  "evidence_path": "YOUR_SCAN_APPROVED_TEST_FILE"
}
```

Zero IDs are placeholders, not fixtures. Replace all values with actual staging
records. Set `SF_BASE_URL` to your staging server, then run:

```bash
node ci/member_lifecycle_browser.mjs
```

Also run the ORM/HTTP suite. The browser smoke is not the full adversarial suite:
include payer-only access, unrelated account, revoked club representative,
relationship expiry, cross-company access, direct `/web/content` attempts against
current/archive/claim attachments, duplicate account conflicts and overlapping
membership conflicts. Retain evidence of the exact attempted requests and outcomes.

## Required usability sessions


Recruit at least 10 distinct novice users. Do not coach them during scored tasks.
For each user:

1. Manage two dependants, focusing on A then B. Renew A and upload B's requested
   evidence. Record any wrong-person action, including actions caught by the server.
2. Renew a membership and explain what is pending and who activates it.
3. Resolve one missing requirement, such as requesting the missing licence or
   uploading the named person's required evidence. Explain that request/upload is
   not activation/approval.
4. Explain membership versus sporting eligibility using an active membership with
   a draft/expired licence and a missing safeguarding requirement.

Score `completed=true` only when both ordinary renewal and document tasks finish;
`assisted=false` only when no procedural help was given. Record
`membership_vs_eligibility_correct` and `wrong_person_actions` for every participant.
Use pseudonymous participant codes, not unnecessary personal data.

Reviewer/admin scenarios:

- Open a document snapshot, replace its source, then attempt old approval: reject.
- Resolve a non-overlapping duplicate identity: retain both players, all licence/
  result history, moved membership IDs, original evidence revisions and decision.
- Attempt consolidation with overlapping memberships or active duplicate login:
  block without deletion or permission union.
- Revoke guardian access with the browser still signed in: subsequent upload,
  download and focused-person request must fail.

## Success metric gate


Copy `ci/member_lifecycle_acceptance.template.json` to an observations file. Fill
only actual measured results. For each adversarial case record execution count and
actual wrong-person actions, stale approvals, unauthorised document accesses and
new duplicate identities. An unexecuted case or missing counter fails the gate.

For at least 10 matched routine renewals, record baseline and candidate completion
and administrative touches. Count each human administrative interaction consistently,
including chasing, correction, review and activation. Compare equivalent cases;
do not omit unsuccessful renewals or treat unfinished work as zero touches.

```bash
python ci/evaluate_member_lifecycle.py YOUR_OBSERVATIONS.json \
  --output YOUR_ACCEPTANCE_RESULT.json
```

The gate requires:

- At least 90% unassisted ordinary task completion, with at least 10 distinct users.
- At least 90% correct membership-versus-eligibility explanations.
- Zero wrong-person actions in both human family sessions and adversarial cases.
- Zero stale approvals and unauthorised document accesses.
- At least 50% reduction in mean administrative touches against completed baseline.
- Zero duplicate identities in the defined matching and concurrency scenarios.

Record candidate commit and observation date with the results. Unit-test fixtures
for the evaluator are synthetic test inputs, not observed success metrics.
