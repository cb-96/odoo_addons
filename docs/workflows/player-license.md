# Workflow: Player License Lifecycle

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

End-to-end management of a player's federation license — from creation through
seasonal activation, expiry, suspension checks, and reinstatement.

## Overview

Every player who competes in a federation tournament must hold a valid
**player license** (`federation.player.license`) scoped to the current season.
A license certifies the player's eligibility, links them to their club, and
records their category (Senior, Youth, Junior, Cadet). The license state machine
drives eligibility checks used by the roster and rules engines.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_people` | Player records and license model |
| `sports_federation_base` | Season and club master data |
| `sports_federation_rules` | Eligibility service (`federation.eligibility.service`) |
| `sports_federation_rosters` | Roster-line license validation (`assignment_ready`) |
| `sports_federation_officiating` | Suspension check integration |
| `sports_federation_discipline` | Suspension sanctions that block eligibility |
| `sports_federation_finance_bridge` | License-fee finance events |
| `sports_federation_notifications` | Expiry and reinstatement notifications |

## Models

| Model | Key Fields |
|-------|-----------|
| `federation.player.license` | `name` (license number), `player_id`, `season_id`, `club_id`, `state`, `category`, `issue_date`, `expiry_date` |
| `federation.player` | `state` (`active` / `inactive` / `suspended`), `is_eligible` (computed) |

## License States

```
draft → active → expired
      ↘ cancelled
active → cancelled
```

| State | Meaning |
|-------|---------|
| `draft` | License created but not yet active — player is not eligible |
| `active` | License is valid — player is eligible for roster inclusion |
| `expired` | Expiry date passed and license was not renewed — player is not eligible |
| `cancelled` | License administratively voided — player is not eligible |

## Step-by-Step Flow

### 1. License Creation

**Actor**: Federation administrator or club representative (portal)
**Module**: `sports_federation_people`

1. Navigate to **Federation > Clubs & People > Players & Licensing > Configuration > Licenses** and click **New**, or
   open the player record and click **Create License** from the **Licenses** tab.
2. Fill in:
   - **License Number** — unique identifier (e.g. `LIC-2026-00042`)
   - **Player** — select the player
   - **Season** — must be an open season
   - **Club** — the club the player is registered under this season
   - **Category** — `Senior`, `Youth`, `Junior`, or `Cadet`
   - **Issue Date** — defaults to today
   - **Expiry Date** — set to the season end date or a specific date
3. Save. The license starts in **`draft`** state.

**Uniqueness constraint**: one license per player per season.
Attempting a second license for the same player/season raises a validation error.

### 2. Season Activation

**Actor**: Federation administrator
**Module**: `sports_federation_people`

1. After verifying any required compliance documents or fee payments, click
   **Activate** on the license form.
2. License state transitions: **`draft` → `active`**.
3. The player's computed `is_eligible` field becomes `True`.
4. The player is now available for roster assignment under that season.

**Finance event**: if `sports_federation_finance_bridge` is installed, a license
fee event (`category = registration`) is created automatically on activation.

### 3. Eligibility Check Integration

**Actor**: System (called by roster and rules modules)
**Module**: `sports_federation_rules`

The `federation.eligibility.service` is the authoritative eligibility oracle:

1. On roster-line creation or tournament participant validation, the service
   calls `_is_player_eligible(player, season)`.
2. The service checks:
   - `federation.player.license` with `state = active` and matching `season_id`.
   - `federation.player.state` not equal to `suspended`.
   - No active suspension sanction from `sports_federation_discipline`.
3. If any check fails, the roster line is marked `assignment_ready = False` with
   a human-readable `readiness_feedback`.

### 4. Expiry Rules

**Actor**: System
**Module**: `sports_federation_people`

- An active license whose `expiry_date` has passed is shown with a visual
  warning on the player and license forms.
- The system does **not** auto-transition `active → expired`. An administrator
  must manually click **Mark Expired** or run the `_cron_expire_licenses`
  scheduled action (if configured).
- Expired licenses are excluded from eligibility checks.

**Season close**: when a season is closed, it is good practice to run
`_cron_expire_licenses` immediately to clean up all active licenses tied to that
season.

### 5. Suspension Check Integration

**Actor**: System
**Module**: `sports_federation_discipline`

1. When a disciplinary sanction with `sanction_type = suspension` and
   `state = active` exists for a player, the eligibility service flags that
   player as ineligible regardless of license state.
2. The player's `state` is set to `suspended` by the discipline module's
   enforcement action.
3. All roster lines for that player in upcoming matches are flagged
   `assignment_ready = False`.

### 6. Reinstatement Path

**Actor**: Federation administrator
**Module**: `sports_federation_people` + `sports_federation_discipline`

A player can be reinstated after a suspension or licence cancellation:

1. **Suspension ended**: the discipline module expires the suspension sanction
   and calls `action_reactivate` on the player, transitioning
   `suspended → active`.
2. **Cancelled licence renewed**: create a new draft licence for the player,
   activate it. The old cancelled licence remains in history.
3. **Expired licence renewed for the same season**: cancel the expired licence,
   create a new draft licence, and activate it. (The unique constraint is per
   player/season so the old expired record must be cancelled first.)
4. On reinstatement, the player's `is_eligible` recomputes automatically.

**Notification**: if `sports_federation_notifications` is installed, the
reinstatement triggers a notification to the club contact on record.

## Eligibility Summary

A player is eligible to compete when **all** of the following are true:

- `federation.player.state = active`
- At least one `federation.player.license` with `state = active` and
  `season_id` matching the competition season
- No active suspension sanction

## State Diagram

```
License: draft → active → expired (manual or cron)
               ↘ cancelled
         active → cancelled

Player:  active → suspended → active (reinstatement)
         active → inactive
```
