# Workflow: Standings Lifecycle

Automatic and manual standing recomputation, freeze points, website
publication, and the impact of official-result changes on standings tables.

## Overview

Standings are derived from results that still have
`include_in_official_standings = True`. They recompute automatically when a
result becomes official, can be recomputed manually at any time, and are
frozen when the authoritative ranking for a stage must be locked. Public
visibility is separate from the standings state itself and is controlled
through `website_published`.

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
| `federation.standings` | `tournament_id`, `stage_id`, `group_id`, `state`, `computed_on`, `website_published`, `public_title` |
| `federation.standings.line` | `team_id`, `position`, `points`, `played`, `won`, `drawn`, `lost`, `goals_for`, `goals_against`, `goal_diff` |

## Standing States

```
draft → computed → frozen
```

| State | Meaning |
|-------|---------|
| `draft` | Standings record exists but has not been computed |
| `computed` | Standings are up to date with the currently official results |
| `frozen` | Standings are locked; no further recompute will change them |

`website_published = True` controls whether the standing is visible on the
public site. It does not create a separate standings workflow state.

## Step-by-Step Flow

### 1. Automatic Recompute Trigger

**Actor**: System (triggered by result approval)
**Module**: `sports_federation_result_control` → `sports_federation_standings`

When a match result is approved (`result_state = approved`):

1. `include_in_official_standings` is set to `True` on the match record.
2. The result approval method calls
   `federation.standings._trigger_recompute(tournament_id, stage_id, group_id)`.
3. Any `federation.standings` record linked to the same tournament / stage /
   group that is in `draft` or `computed` state is queued for recompute.
4. The standings table is rebuilt from scratch from all approved results
   in that scope.
5. After recompute, the standings transition to `computed`.

**Frozen standings are not recomputed**. If a result is approved after the
standings have been frozen, a warning appears on the match form but the
standings are not changed.

### 2. Manual Recompute

**Actor**: Federation administrator
**Module**: `sports_federation_standings`

When results are corrected or the automatic trigger did not fire (e.g. an edge
case during bulk import):

1. Navigate to **Federation → Standings** and open the relevant standings record.
2. Click **Recompute** (only available in `draft` or `computed` states, never on
   `frozen` or `published`).
3. The standings engine rebuilds all lines from approved results.
4. State transitions to `computed`.

### 3. Freeze Decision

**Actor**: Federation administrator (Federation Manager group)
**Module**: `sports_federation_standings`

Standings are frozen at a natural boundary — end of group stage, end of regular
season, or after the last knockout round of a stage:

1. Open the standings record in `computed` state.
2. Click **Freeze**.
3. State transitions: `computed → frozen`.
4. Frozen standings will not be touched by any subsequent result approval in
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

1. With standings in `computed` or `frozen` state, publish the record from the
   Website tab.
2. `website_published` is set to `True`.
3. The standings page at `/tournaments/<slug>/standings` now reflects the
   table.

If `sports_federation_notifications` is installed, a notification is dispatched
to club contacts when standings for their tournament are published.

**Unpublishing**: set `website_published = False` to pull the standings from
the public site without changing the `state`. This is useful when a dispute or
late correction requires re-review.

### 5. Contested Result Impact on Standings

**Actor**: Club representative or federation official → Governance officer
**Module**: `sports_federation_result_control` + `sports_federation_governance`

When a result is contested after standings have been computed:

1. `result_state` moves to `contested` and
   `include_in_official_standings` becomes `False`.
2. Any standings in `draft` or `computed` scope are recomputed automatically
   and drop the result.
3. If the standing is `frozen`, federation staff must decide whether to leave
   the frozen table in place during review or deliberately unfreeze or
   force-recompute it after governance review.
4. If the standing is public (`website_published = True`) and the table should
   be withdrawn during review, unpublish it separately. Publication is not a
   standings state.
5. A governance override request may document the review, but it does not keep
   a contested result official.

## Contested Results and the Frozen Table

| Standing status | Operator action |
|----------------|-----------------|
| `draft` / `computed` | Automatic recompute removes the contested result |
| `frozen` | Federation manager decides whether to unfreeze or force-recompute after review |
| `website_published = True` | Unpublish separately if the public table should be hidden during review |

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
