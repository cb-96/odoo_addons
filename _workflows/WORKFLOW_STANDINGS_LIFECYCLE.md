# Workflow: Standings Lifecycle

Automatic and manual standing recomputation, freeze points, publication
approval, and the impact of contested results on standings tables.

## Overview

Standings are derived from approved match results. They recompute automatically
when a result is approved, can be recomputed manually at any time, and are
frozen when the authoritative ranking for a stage must be locked. Before
standings appear on the public site, a publication approval step ensures the
federation has reviewed the table.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_standings` | Standings model, recompute engine |
| `sports_federation_result_control` | Result approval triggering recompute |
| `sports_federation_tournament` | Tournament, stage, match records |
| `sports_federation_governance` | Override requests for disputed standings |
| `sports_federation_public_site` | Publication (`website_published`) |
| `sports_federation_notifications` | Notification on standings publication |

## Models

| Model | Key Fields |
|-------|-----------|
| `federation.standings` | `tournament_id`, `stage_id`, `group_id`, `state`, `website_published`, `frozen_on`, `published_on` |
| `federation.standings.line` | `team_id`, `position`, `points`, `played`, `won`, `drawn`, `lost`, `goals_for`, `goals_against`, `goal_diff` |

## Standing States

```
draft → computing → ready → frozen
                  ↘ published
```

| State | Meaning |
|-------|---------|
| `draft` | Standings record exists but has not been computed |
| `computing` | Recompute is in progress (transient; typically brief) |
| `ready` | Standings are up to date with all approved results |
| `frozen` | Standings are locked; no further recompute will change them |
| `published` | Standings are live on the public site |

## Step-by-Step Flow

### 1. Automatic Recompute Trigger

**Actor**: System (triggered by result approval)
**Module**: `sports_federation_result_control` → `sports_federation_standings`

When a match result is approved (`result_state = approved`):

1. `include_in_official_standings` is set to `True` on the match record.
2. The result approval method calls
   `federation.standings._trigger_recompute(tournament_id, stage_id, group_id)`.
3. Any `federation.standings` record linked to the same tournament / stage /
   group that is in `draft` or `ready` state is queued for recompute.
4. The standings table is rebuilt from scratch from all approved results
   in that scope.
5. After recompute, the standings transition to `ready`.

**Frozen standings are not recomputed**. If a result is approved after the
standings have been frozen, a warning appears on the match form but the
standings are not changed.

### 2. Manual Recompute

**Actor**: Federation administrator
**Module**: `sports_federation_standings`

When results are corrected or the automatic trigger did not fire (e.g. an edge
case during bulk import):

1. Navigate to **Federation → Standings** and open the relevant standings record.
2. Click **Recompute** (only available in `draft` or `ready` states, never on
   `frozen` or `published`).
3. The standings engine rebuilds all lines from approved results.
4. State transitions to `ready`.

### 3. Freeze Decision

**Actor**: Federation administrator (Federation Manager group)
**Module**: `sports_federation_standings`

Standings are frozen at a natural boundary — end of group stage, end of regular
season, or after the last knockout round of a stage:

1. Open the standings record in `ready` state.
2. Click **Freeze**.
3. `frozen_on` timestamp is recorded.
4. State transitions: `ready → frozen`.
5. Frozen standings will not be touched by any subsequent result approval in
   that scope.

**Who can freeze**: only users in the `group_federation_manager` security group
can freeze standings.

**When to freeze**: freeze only after all matches in the stage are `done` and
all results are `approved`. Freezing with unapproved results creates an
incomplete official table.

### 4. Publication Approval

**Actor**: Federation administrator
**Module**: `sports_federation_standings` → `sports_federation_public_site`

Before standings appear on the public website, a publication approval step
provides a human review checkpoint:

1. With standings in `frozen` state (or `ready` for live tournament standings),
   click **Publish**.
2. Confirm the dialog. `website_published` is set to `True` and
   `published_on` timestamp is recorded.
3. State transitions to `published`.
4. The standings page at `/tournaments/<slug>/standings` now reflects the table.

If `sports_federation_notifications` is installed, a notification is dispatched
to club contacts when standings for their tournament are published.

**Unpublishing**: set `website_published = False` to pull the standings from
the public site without changing the `state`. This is useful when a dispute
requires re-review.

### 5. Contested Result Impact on Standings

**Actor**: Club representative or federation official → Governance officer
**Module**: `sports_federation_result_control` + `sports_federation_governance`

When a result is contested after standings have been computed:

1. A `federation.override_request` (type `result_correction`) is raised
   (see [WORKFLOW_APPEAL_DISPUTE.md](WORKFLOW_APPEAL_DISPUTE.md)).
2. **While the override is in `submitted` state**:
   - The result remains `approved` and **continues to count** in standings.
   - Standings are not automatically rolled back.
3. **If the override is approved and implemented**:
   - The result is corrected (scores updated or forfeit applied).
   - The result approval is re-triggered by the administrator.
   - Standings in `ready` or `draft` state are recomputed automatically.
   - If standings are `frozen`, the administrator must unfreeze them
     (federation manager only), trigger a manual recompute, then re-freeze.
4. **Contested results should not remain in `approved` state indefinitely**:
   governance policy is to resolve all override requests before standings are
   frozen.

## Contested Results and the Frozen Table

| Standings State | Contested Result Action |
|----------------|------------------------|
| `draft` / `ready` | Automatic recompute after result correction |
| `frozen` | Administrator must unfreeze → recompute → re-freeze |
| `published` | Administrator must unpublish → unfreeze → recompute → re-freeze → re-publish |

## Summary of Access Control

| Action | Required Group |
|--------|---------------|
| Manual recompute | `group_federation_manager` |
| Freeze standings | `group_federation_manager` |
| Publish / unpublish | `group_federation_manager` |
| View standings | `group_federation_user` (backend), public (website) |

## Related Workflows

- [WORKFLOW_RESULT_PIPELINE.md](WORKFLOW_RESULT_PIPELINE.md) — Result approval that triggers automatic recompute.
- [WORKFLOW_APPEAL_DISPUTE.md](WORKFLOW_APPEAL_DISPUTE.md) — Appeal and dispute process for contested results.
- [WORKFLOW_PUBLIC_PUBLICATION.md](WORKFLOW_PUBLIC_PUBLICATION.md) — Broader public-site publication workflow.
