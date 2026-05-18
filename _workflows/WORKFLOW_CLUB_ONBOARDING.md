# Workflow: Club Onboarding

End-to-end process for registering a new club with the federation — from initial
request through compliance document intake, bank-details entry, first-season
registration, and portal access grant.

## Overview

A new club must be formally onboarded before it can enter teams in tournaments.
Onboarding spans four areas: master-data setup, compliance document collection,
finance details, and portal access for the club representative. These steps can
run partly in parallel once the club record exists.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_base` | Club, team, and season master data |
| `sports_federation_compliance` | Document requirement tracking |
| `sports_federation_portal` | Club representative portal access |
| `sports_federation_finance_bridge` | Bank details, registration fee event |
| `sports_federation_notifications` | Welcome and missing-document notifications |

## Step-by-Step Flow

### 1. New Club Request

**Actor**: Club applicant (off-system) → Federation administrator
**Module**: `sports_federation_base`

The federation receives a new-club application through its standard intake
channel (email, paper form, or future portal form). The federation administrator
creates the club record:

1. Navigate to **Federation → Configuration → Clubs** and click **New**.
2. Fill in:
   - **Name** — official club name
   - **Code** — short unique code (e.g. `MFC`)
   - **Email**, **Phone**, **Website** (optional)
   - **Address** — postal address for correspondence
3. Save. The club starts with `active = True` and no additional state.

At this point the club exists in the system but is not yet enrolled in any season
and has no compliance documents or portal access.

### 2. Federation Staff Review

**Actor**: Federation administrator
**Module**: `sports_federation_base` + `sports_federation_compliance`

Before proceeding with compliance intake, the administrator performs a background
review:

- Verify the club is not a duplicate (search by name and code).
- Confirm the founding documents meet federation bylaws.
- Confirm at least one responsible contact person has been nominated.

No formal review state exists on the club record itself. Use the chatter
(Discuss tab on the club form) to record review notes.

### 3. Compliance Document Intake

**Actor**: Federation administrator or club contact
**Module**: `sports_federation_compliance`

Create one `federation.compliance.submission` per document requirement that
applies to clubs (`required_for_all = True` for the `club` target model):

Common requirements at onboarding:

| Requirement | Expiry? | Notes |
|------------|---------|-------|
| Public Liability Insurance | Yes (annual) | Minimum coverage amount per federation rules |
| Club Registration Certificate | No | Official registration with national authority |
| Bank Account Confirmation Letter | No | Matches bank details to be entered |
| Club Rules & Constitution | No | Signed copy |

For each document:

1. Navigate to **Federation → Compliance → Document Submissions**.
2. Create a submission linked to the club and the relevant requirement.
3. Attach the scanned or PDF document.
4. Submit: state `draft → submitted`.
5. The compliance officer reviews and approves: state `submitted → approved`.

If `sports_federation_notifications` is installed, an approval confirmation is
sent to the club contact on each approval.

### 4. Bank Details Entry

**Actor**: Federation administrator
**Module**: `sports_federation_finance_bridge`

1. On the club form, open the **Finance** tab (added by `sports_federation_finance_bridge`).
2. Enter bank account details (IBAN, bank name, account holder name).
3. These details are used when generating registration-fee finance events for
   accounting integration exports.

### 5. First Season Registration

**Actor**: Club administrator or club representative
**Module**: `sports_federation_base` + `sports_federation_portal`

Once compliance documents are approved, the club can register for the current
season:

**Via back-office**:

1. Navigate to **Federation → Registrations → Season Registrations**.
2. Create a registration record for the club's first team in the current season.
3. State: `draft → submitted → confirmed`.

**Via portal (if portal module is installed)**:

1. Club representative logs into the portal.
2. Navigates to the Season Registrations section.
3. Submits a registration request (creates in `submitted` state).
4. Federation administrator confirms from the back office.

A registration-fee finance event is created automatically on confirmation.

### 6. Club Representative Portal Access Grant

**Actor**: Federation administrator
**Module**: `sports_federation_portal`

1. Navigate to **Federation → Portal → Club Representatives**.
2. Create a `federation.club.representative` record:
   - **Club** — the newly onboarded club
   - **User** — invite the contact as an Odoo portal user (`res.users` with
     the portal group), or select an existing portal user
   - **Role Type** — select the appropriate role (e.g. `Competition Contact`,
     `Finance Contact`)
3. Save.
4. The representative is now linked to the club. Portal record rules limit them
   to records belonging to their club.

**Sending the portal invitation**: use the standard Odoo **Grant portal access**
wizard from the contact (res.partner) record associated with the representative's
user. This sends the portal invitation email.

Once the invitation is accepted, the representative can:

- Submit season registration requests
- Upload compliance documents
- View their club's roster and match schedule
- Submit match result sheets

## Checklist

| Step | Owner | Required before |
|------|-------|----------------|
| Club record created | Federation admin | All other steps |
| Compliance docs approved | Compliance officer | First tournament entry |
| Bank details entered | Federation admin | Finance event export |
| Season registration confirmed | Federation admin | Tournament participation |
| Portal user invited | Federation admin | Club representative self-service |

## Related Workflows

- [WORKFLOW_SEASON_REGISTRATION.md](WORKFLOW_SEASON_REGISTRATION.md) — Full season-registration process including team enrolment and player licensing.
- [WORKFLOW_COMPLIANCE_MANAGEMENT.md](WORKFLOW_COMPLIANCE_MANAGEMENT.md) — Document submission and review details.
- [WORKFLOW_FINANCIAL_TRACKING.md](WORKFLOW_FINANCIAL_TRACKING.md) — Registration fee event creation.
