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

## Submission and recovery

The club portal and public competition registration page submit through the
same portal command. It checks that the selected window belongs to the division,
is open now (including its open/close timestamps), that the team is in the
current representative's scope and eligible, that the team has no active entry,
and that the division has remaining capacity.

Entries progress through `draft`, `submitted`, and `approved`, or are marked
`rejected`/`withdrawn`. A returned entry is restored to `draft` with the
federation's review note. Representatives may update the submission note and
resubmit draft, rejected, or withdrawn entries while the original window is
open. Resubmitting a withdrawn entry reuses the existing row; the database
constraint remains one entry per team and window. Approved entries cannot be
withdrawn directly. Only federation registration roles can approve, return, or
reject entries; club representatives cannot finalize participant sets.

## Regression tests

The regression coverage is in
`tests/test_registration_team_selection.py`. Run it with the repository's
module-level Odoo test workflow after installing the registration addon and its
declared dependencies.
