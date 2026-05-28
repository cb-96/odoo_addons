# Workflow: Season Registration

End-to-end process for setting up a new season and registering clubs, teams, and
players — from season creation through club enrolment to individual licensing.

## Overview

Every competitive year begins with a **season** that scopes all competitions,
registrations, rosters, and licenses. Clubs register for the season, enrol their
teams, and players receive licenses that certify their eligibility to compete.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_base` | Season, club, team, and season-registration models |
| `sports_federation_people` | Player records and license creation |
| `sports_federation_portal` | Club representative self-service registration |
| `sports_federation_compliance` | Document requirements linked to registration |
| `sports_federation_finance_bridge` | Registration fee events |
| `sports_federation_notifications` | Registration reminders and confirmations |

## Step-by-Step Flow

### 1. Season Creation

**Actor**: Federation administrator
**Module**: `sports_federation_base`

1. Open the **Seasons** screen from the backend setup area.
2. Create a new season with name, code, and date range (e.g. "2025-2026").
3. Set the season state to **open**.

The season record becomes the scoping key for all registrations, tournaments,
rosters, and licenses throughout the year.

### 2. Club Registration Opening

**Actor**: Federation administrator
**Module**: `sports_federation_base`

1. Open the **Season Registrations** screen from the backend setup area.
2. Create registration records (one per team) or let clubs self-register via the portal.
3. Each registration links a team and its club to an open season.

Registration states: `draft` → `submitted` → `confirmed` / `cancelled`.

### 3. Portal Self-Service (Optional)

**Actor**: Club representative (portal user)
**Module**: `sports_federation_portal`

1. Club representative logs into the portal.
2. Navigates to the federation registration section.
3. Submits their club's season registration request.
4. Adds supporting notes when needed.
5. Registration is created in `submitted` state for federation review.

### 4. Registration Review & Approval

**Actor**: Federation administrator
**Module**: `sports_federation_base`

1. Review submitted registrations from the backend review screen.
2. Verify club ownership, season status, and any federation prerequisites.
3. **Confirm** the registration or **reject** it back to `draft` with a rejection reason.
4. Confirmed teams are eligible to enrol players and proceed into competition operations.
5. The season and registration forms now surface that same order of operations
  inline: draft seasons point operators toward registrations, open seasons warn
  when registrations are still missing or pending, and confirmed registrations
  expose a direct **Open Team Rosters** handoff for the next operational step.

There is no persistent `rejected` season-registration state in the current model. Rejection is represented by the record returning to `draft` while keeping `rejection_reason` for follow-up.

### 5. Team Enrolment

**Actor**: Club administrator or federation staff
**Module**: `sports_federation_base`

1. Under each confirmed club registration, create or confirm teams for the season.
2. Teams inherit the club's season registration scope.
3. Teams become available for tournament participation and roster creation.
4. When roster preparation is the next task, use **Open Team Rosters** from the
  confirmed registration. The action opens the roster list with the current
  team, season, competition, and rule-set context prefilled.

### 6. Player Registration & Licensing

**Actor**: Federation administrator
**Module**: `sports_federation_people`

Player licenses are the formal proof of a player's eligibility to compete in a
given season. Each license is scoped to one player, one season, and one club.

#### License Creation

1. Create or locate the player record (`federation.player`) with club affiliation.
2. Navigate to the player's **Licenses** tab and click **New**, or go to
   **Federation → People → Player Licenses** and create from there.
3. Fill in:
   - **Season** (must be open)
   - **Club** (must match the player's current club)
   - **Issue date** and **Expiry date** (expiry must be after issue date)
   - **Category**: `senior` | `youth` | `junior` | `cadet`
   - Optional eligibility notes
4. An auto-generated license number is assigned via `ir.sequence` (`FED-LIC-XXXXX`).

Uniqueness constraint: one license per player per season (`player_id, season_id`).

#### License Status Rules

The full player-license lifecycle is authoritative in
[WORKFLOW_PLAYER_LICENSE.md](WORKFLOW_PLAYER_LICENSE.md).

For season-registration work, the relevant operator rule is simpler:

- Only an `active` license satisfies roster and match-sheet readiness.
- `expired` or `cancelled` licenses block readiness until a valid license
  exists or the record is corrected and reactivated.
- The system does not auto-expire licenses. Administrators manage expiry or
  cancellation explicitly.

#### License Eligibility Impact

- Roster readiness check (`ready_for_activation`) blocks roster activation if any
  roster line's player has no `active` license for the same season.
- Match sheet readiness check applies the same rule at squad-submission time.
- A player with a `cancelled` or `expired` license cannot appear on active
  rosters or submitted match sheets for the relevant season.

### 7. Compliance Document Collection

**Actor**: Club representative or federation staff
**Module**: `sports_federation_compliance`

1. Federation defines document requirements per entity type (club, player, etc.).
2. Clubs upload required documents (insurance, safety certificates, etc.).
3. Federation staff reviews submissions: `submitted` → `approved` / `rejected`.
4. Compliance checks are run to flag missing or expired documents.

### 8. Fee Recording

**Actor**: Federation administrator
**Module**: `sports_federation_finance_bridge`

1. Upon registration confirmation, a finance event is created for the registration fee.
2. The default catalogue fee type code is `season_registration` (created on demand
    as "Season Registration Fee" if it does not exist yet).
3. Finance event follows: `draft` → `confirmed` → `settled` / `cancelled`.

### 9. Notifications

**Actor**: System (automated)
**Module**: `sports_federation_notifications`

- Registration confirmation and rejection emails are logged and sent to the submitting club representative.
- Reminders for incomplete or stale draft registrations (cron job).
- Missing-document notices triggered by compliance checks.

## State Diagram

```
Season: draft → open → closed

Registration: draft → submitted → confirmed
                                 → cancelled
                                 ↘ draft (via rejection)

License: draft → active → expired
                        → cancelled
```

## Key Decision Points

| Question | Outcome |
|----------|---------|
| Are all compliance documents submitted? | Block approval until compliant |
| Is the registration fee paid? | Registration can proceed but fee remains tracked |
| Has the club been sanctioned? | Governance override may be needed |

## Related Workflows

- [Tournament Lifecycle](WORKFLOW_TOURNAMENT_LIFECYCLE.md) — tournaments open to registered clubs
- [Compliance Management](WORKFLOW_COMPLIANCE_MANAGEMENT.md) — document collection detail
- [Financial Tracking](WORKFLOW_FINANCIAL_TRACKING.md) — fee handling detail
