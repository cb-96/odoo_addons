# Portal Ownership Test Matrix

Date: 2026-06-01
Scope: Item 7 (Portal Ownership Boundary Hardening)

## Objective

Ensure portal access remains deny-by-default across representative-, team-, and official-scoped flows, including direct ID-guess and elevated helper entrypoints.

## Matrix

| Surface | Positive scope test | Negative scope test | Source tests |
|---|---|---|---|
| Club representative ownership | own club/team records visible | cross-club records blocked | `tests/test_club_representative.py`, `tests/test_portal_ownership_guard.py` |
| Team rosters | own roster + lines visible/editable | foreign roster/line blocked (403/model guard) | `tests/test_roster_portal_access.py`, `tests/test_portal_access_denied.py` |
| Season registrations | own team registrations writable | foreign-club submission blocked | `tests/test_season_registration.py`, `tests/test_portal_ownership_guard.py` |
| Tournament operations board | visible-tournament payload includes only scoped matches | out-of-scope tournament/match action blocked | `tests/test_tournament_operations.py` |
| Match result portal pages | own-club result flow allowed | foreign match/result flow denied | `tests/test_result_portal_access.py` |
| Officiating assignments | linked official can view/respond | unlinked user cannot access assignments | `tests/test_officiating_portal_access.py` |
| Team-scoped representative filters | assigned team scope honored | same-club but unassigned team paths denied | `tests/test_team_portal_access.py` |
| Player portal access | scoped players visible | hidden players blocked | `tests/test_player_portal_access.py` |

## Deny-by-default Guards

The following model/service-level guards are mandatory and regression-tested:

- `federation.portal.privilege.portal_write(..., scope_domain=...)`
- `federation.portal.privilege.portal_call(..., scope_domain=...)`
- `federation.portal.privilege._assert_portal_owns(...)`
- roster helper `_portal_assert_scope_access(...)`
- roster helper `_portal_assert_registration_access(...)`

Any new portal write route must prove ownership through one of these guards before elevated writes.
