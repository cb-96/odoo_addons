# Workflow: Compliance Management

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

Document requirements, submissions, review, and compliance checking across all
federation entities.

## Overview

The federation requires clubs, players, referees, and venues to maintain various
documents (insurance certificates, safety reports, medical clearances, etc.).
This workflow covers how requirements are defined, how documents are submitted
and reviewed, and how compliance is monitored.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_compliance` | Requirements, submissions, compliance checks |
| `sports_federation_base` | Clubs |
| `sports_federation_people` | Players |
| `sports_federation_officiating` | Referees |
| `sports_federation_venues` | Venues |
| `sports_federation_portal` | Club representatives (as a target entity) |
| `sports_federation_notifications` | Missing-document notifications |
| `mail` | Chatter on submissions |

## Step-by-Step Flow

### 1. Requirement Definition

**Actor**: Federation administrator
**Module**: `sports_federation_compliance`

1. Navigate to **Federation > Administration > Configuration > Document Requirements**.
2. Create requirements specifying:
   - Name and unique code
   - Target model: `club`, `player`, `referee`, `venue`, or `club_representative`
   - Whether it applies to all entities of that type (`required_for_all`)
   - Whether a submission must include an expiry date
   - Default validity period in days
   - Detailed description of what's needed

**Examples**:

| Requirement | Target | Expiry? |
|------------|--------|---------|
| Public Liability Insurance | Club | Yes (annual) |
| Medical Certificate | Player | Yes (seasonal) |
| Referee Badge | Referee | Yes (certification period) |
| Safety Inspection Report | Venue | Yes (annual) |

### 2. Document Submission

**Actor**: Club representative, entity owner, or federation staff
**Module**: `sports_federation_compliance`

1. Navigate to **Federation > Finance & Assurance > Compliance > Submissions**.
2. Create a submission linked to:
   - The requirement being fulfilled
   - Exactly one target entity (club, player, referee, venue, or representative)
3. Upload the document as an attachment.
4. Set issue date and expiry date (if required by the requirement).
5. Submit: state moves from `draft` → `submitted`.

The system enforces that exactly one target entity field is filled in.

### 3. Submission Review

**Actor**: Federation compliance officer
**Module**: `sports_federation_compliance`

1. Review submitted documents in the submission queue.
2. Verify document authenticity, completeness, and validity dates.
3. Decision:
   - **Approve**: state → `approved`. Document is now valid.
   - **Reject**: state → `rejected`. Entity must resubmit.
   - **Request Replacement**: state → `replacement_requested`. Current document
     is nearing expiry or has issues.
4. Reviewer and review timestamp are recorded.

### 4. Expiry Monitoring

**Actor**: System (automated)
**Module**: `sports_federation_compliance`

1. The `is_expired` computed field automatically flags submissions where
   `expiry_date < today`.
2. Expired submissions show a **ribbon** in the form view for visual alerting.
3. State transitions to `expired` for documents past their expiry date.

### 5. Compliance Check Execution

**Actor**: Federation administrator
**Module**: `sports_federation_compliance`

1. Run compliance checks for a specific entity type or across all types.
2. For each entity and applicable requirement, the system checks whether a valid
   (approved, non-expired) submission exists.
3. Creates a **compliance check** record with status:
   - `compliant` — Valid submission exists
   - `missing` — No submission at all
   - `pending` — Submission exists but not yet approved
   - `expired` — Submission approved but past expiry date
   - `non_compliant` — Submission was explicitly rejected or otherwise failed policy review

### 6. Notification & Follow-Up

**Actor**: System / federation staff
**Module**: `sports_federation_notifications`

1. Compliance check results identify gaps.
2. Missing-document notification emails are sent to responsible parties.
3. Club representatives receive notices via portal or email.
4. Stale submissions trigger reminder notifications.

### 7. Re-Submission

**Actor**: Entity owner
**Module**: `sports_federation_compliance`

1. After rejection or expiry, the entity owner uploads a new document.
2. Creates a new submission (the old one remains for audit).
3. New submission follows the same review cycle.

### 8. Operational Reporting

**Actor**: Federation administrator
**Module**: `sports_federation_reporting`

1. Open the reporting menu for compliance status summaries and recurring report schedules.
2. Use the compliance summary report to review `missing`, `pending`, `expired`, and `non_compliant` totals without querying the database directly.
3. When a recurring weekly or monthly review is required, create a report schedule so the latest CSV snapshot is generated inside Odoo.

## State Diagram

```
Submission: draft → submitted → approved → expired
                              → rejected
                              → replacement_requested

Compliance Check: compliant / missing / pending / expired / non_compliant
                  (point-in-time status, regenerated each run)
```

## Multi-Entity Coverage

The same framework covers all federation entity types:

| Entity | Example Requirements |
|--------|---------------------|
| Club | Insurance, registration documents, facility certificates |
| Player | Medical certificate, residency proof, parental consent (minors) |
| Referee | Certification badge, fitness test, background check |
| Venue | Safety inspection, capacity certificate, accessibility report |
| Club Representative | Identity verification, authorisation letter |

## Key Decision Points

| Question | Outcome |
|----------|---------|
| Is the document about to expire? | Send renewal reminder |
| Is a required document missing? | Block related operations or send notice |
| Has a rejected document been replaced? | Re-run compliance check |

## Related Workflows

- [Season Registration](season-registration.md) — compliance as registration prerequisite
- [Match Day Operations](match-day-operations.md) — eligibility depends on compliance
- [Governance Override](governance-override.md) — exceptions when compliance is incomplete
