# Portal Ownership Coverage Dashboard

Date: 2026-06-01
Scope: Item 7 (Portal Ownership Boundary Hardening)

## Coverage Summary

| Category | Current status |
|---|---|
| Ownership guard unit tests | Covered |
| Portal controller smoke routes | Covered |
| Cross-club deny scenarios | Covered |
| Out-of-scope operations-board actions | Covered |
| Official-only assignment access | Covered |

## Key Coverage Signals

- Portal ownership guard tests verify ID-guess and missing-scope denial paths.
- Tournament operations tests verify payload scoping and out-of-scope action denial.
- Access-denied tests verify controller-level 403 handling while model-level access still fails closed.

## Coverage Sources

- `tests/test_portal_ownership_guard.py`
- `tests/test_portal_access_denied.py`
- `tests/test_tournament_operations.py`
- `tests/test_roster_portal_access.py`
- `tests/test_result_portal_access.py`
- `tests/test_officiating_portal_access.py`

## Ongoing Rule

Any new ownership-sensitive portal route must include:

1. A positive in-scope test.
2. A negative out-of-scope test.
3. A direct model/helper ownership assertion test if elevated calls are involved.
