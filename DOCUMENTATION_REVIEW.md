# Documentation Consolidation Review

Review date: 2026-08-20
Reviewed source: attached source bundle plus eight separately attached repository-level Markdown files

## Outcome

- 21 Markdown files reviewed
- 15 retained and updated
- 6 recommended for deletion
- no new standalone policy files introduced

## Deleted as redundant

- `sports_federation_notifications/ROADMAP_RC.md`
- `sports_federation_portal/ROADMAP_RC.md`
- `sports_federation_portal/PORTAL_OWNERSHIP_COVERAGE.md`
- `sports_federation_portal/PORTAL_OWNERSHIP_TEST_MATRIX.md`
- `sports_federation_result_control/ROADMAP_RC.md`
- `sports_federation_rules/ROADMAP_RC.md`

### Rationale

The four `ROADMAP_RC.md` files were tiny release snapshots whose remaining bullets are either implemented invariants or broader repository roadmap concerns. Keeping them creates stale, ownerless parallel roadmaps.

The two portal ownership snapshots duplicate each other, the portal README, ADR-0001, and the live tests. Static coverage dashboards become inaccurate whenever tests move. The durable ownership rules are now in the portal README and ADR; test files remain the authoritative coverage map.

## Retained repository-level documents

- `ROADMAP.md`: one current product and engineering roadmap
- `ROUTE_INVENTORY.md`: human-readable critical route ownership
- `INTEGRATION_CONTRACTS.md`: partner and public compatibility policy
- `DATA_RETENTION_POLICY.md`: retention windows and cleanup contract
- `adr/*`: accepted durable architecture decisions

## Important corrections

- Added missing roadmap freshness metadata.
- Replaced the 100-item roadmap backlog with current priorities and explicit statuses.
- Marked the V2 competition ownership decomposition as complete for the current release.
- Added workflow simplification as the primary product priority.
- Removed the unverified `/web/login` ownership row.
- Added the tournament-operations JSON-RPC load and action routes.
- Updated ADR-0001 to describe `federation.portal.privilege` rather than direct `with_user().sudo()` use.
- Consolidated module documentation and removed release-candidate mini-roadmaps.

## Apply and verify

Review the patch, then run:

```bash
git apply --check documentation_consolidation_2026-08-20.patch
git apply documentation_consolidation_2026-08-20.patch
python3 ci/check_doc_freshness.py
python3 ci/check_markdown_links.py
bash ci/run_repo_lint.sh --strict
```

The patch was generated from the supplied snapshot. If the branch has moved, apply individual files from the ZIP or regenerate the patch from the current branch.
