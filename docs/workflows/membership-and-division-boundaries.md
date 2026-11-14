# Membership and division boundaries

## Membership and annual player registration

Person identity says who someone is. Federation membership records their role for
a club and season. Annual player registration/licence approves participation and
owns the annual player fee. Roster lines assign approved players to teams.

Membership is not silently made compulsory. Existing seasons default to no extra
membership prerequisite. With Member and Family Services installed, enable
**Require Federation Membership for Players** on a season only if federation
policy requires it. Approval then requires a reviewed player-person link and an
active player membership for the same club, season and registration company.
A coach/official membership is not a player membership. Cancellation of required
membership blocks fresh roster and live eligibility checks without deleting licences.

Managers see membership status beside annual players and can open the exact scoped
membership workspace. No person identity is guessed, membership activated, or
additional fee generated automatically. Existing identity and membership review
commands remain authoritative. Club representatives still use one annual player
submission journey. Missing membership is returned as an approval blocker.

## Division, competition and game day

The stable technical model federation.tournament remains for compatibility.
An edition-linked record is a division: category, gender, participants, rules and
validity period. Its competition and season are derived from the edition on server
creation and edition assignment, not only through browser onchange. Conflicting
scope writes are rejected. Editions with divisions cannot be reinterpreted as a
different competition/season, and divisions cannot be silently detached.

The division form links to its competition and edition-scoped game-day planning.
Legacy location and single-day/multi-day fields are hidden for edition-linked
records; they remain available on old standalone tournaments. No date, location,
participant, match or result history is deleted or converted automatically.
A new standalone tournament should use the existing competition creation wizard,
with a tournament format, divisions and game days.

Upgrade tournament and member_services if installed after applying the reviewed
annual-player patch and its edge-case tests. The tournament migration normalizes
redundant competition/season pointers to the linked edition. Review discrepancies
on a database copy first; this does not migrate legacy standalone events.

Entry/participant finalization and fixture/match workflows are explicitly out of scope.

## Qualification

Run sf_boundaries and sf_season_players tests in disposable QA, then the full suite.
Test required/optional membership, identity gaps, wrong roles/clubs/seasons/company,
revocation, edition defaults, forged scope writes, frozen editions, legacy records,
and navigation to game days. Runtime and browser qualification remain required.
