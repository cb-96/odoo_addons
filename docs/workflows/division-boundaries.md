# Division boundaries

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

Upgrade tournament after applying the reviewed annual-player patch and its
edge-case tests. The tournament migration normalizes
redundant competition/season pointers to the linked edition. Review discrepancies
on a database copy first; this does not migrate legacy standalone events.

Entry/participant finalization and fixture/match workflows are explicitly out of scope.

## Qualification

Run sf_boundaries and sf_season_players tests in disposable QA, then the full suite.
Test edition defaults, forged scope writes, frozen editions, legacy records,
and navigation to game days. Runtime and browser qualification remain required.
