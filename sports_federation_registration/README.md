# Competition Registration

The Registration Desk manages team entries for a competition edition and division.

## Team selection

When creating or editing a competition entry, the team dropdown is limited to:

- active teams;
- teams eligible for the selected division's category and gender;
- teams that are not already entered in the same registration window.

The available-team list is computed per division and the form applies it as a
selection domain. The model also validates the same rules on create and write,
so direct ORM or API requests cannot bypass the desk filter. Changing a window
clears an existing team selection when it is no longer valid.

Eligibility uses the tournament module's existing `search_eligible_teams()` and
`get_team_eligibility_error()` APIs. No historical registration entries are
rewritten by this filtering; it only affects new selections and invalid direct
writes.

## Regression tests

The regression coverage is in
`tests/test_registration_team_selection.py`. Run it with the repository's
module-level Odoo test workflow after installing the registration addon and its
declared dependencies.
