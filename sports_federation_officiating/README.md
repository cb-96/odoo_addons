# Sports Federation Officiating

Owner: Federation Platform Team
Last reviewed: 2026-09-11
Review cadence: Every release

Referee records, certifications, match assignments, club referee duties, reimbursement requests, and competition-workspace readiness checks.

## Responsibilities

- referee profiles and qualification data
- match referee assignments and response lifecycle
- club referee-duty nominations
- officiating readiness validation
- reimbursement request workflow
- portal and backend actions through the portal addon integration

## Competition integration

The addon extends competition validation through the documented workspace extension contract. Officiating readiness should block or warn at the appropriate lifecycle stage without preventing early schedule construction.

## Security

Officials may only access assignments linked to their portal identity. Club representatives may only manage duties inside their authorized club or team scope. Federation managers retain administrative control.

## Tests

Coverage includes assignment lifecycle, duties, reimbursements, portal access, match-day tours, and workspace integration.

## ownership

Official assignments and club-supplied duties belong to fixture-backed
operational matches. Use **Officiating → Plan Match-Day Officials** to assign a
federation referee or generate club duties for every applicable match in the
current live publication. The removed round wizard must not be reintroduced.


## Automatic club-duty allocation

From **Match Operations → Officiating → Plan Match-Day Officials**, select **Auto-assign Club Duties** for a published match day. The default policy requests four roles per match and assigns all missing roles for that match to one participating club.

The allocator is deterministic and balances the accumulated duty count across eligible clubs. It excludes the two clubs playing the target match. By default it also prefers clubs that have no team playing during the target match window; matches on different courts are treated as concurrent when their published time windows overlap. A configurable fallback can use the least-loaded conflicted club when no non-playing club exists. Disable that fallback when the competition requires a strict non-playing-team rule.

**Preserve existing assignments** is enabled by default. Existing active federation or volunteer referee assignments and existing club duties satisfy their role and are never overwritten. The wizard creates only the missing roles. Duties can be opened immediately for club nomination, or left in draft for operator review.

The `(match, club, role)` duty key is validated before insertion and is also
protected by a database uniqueness constraint. Duplicate submissions therefore
return a normal validation message without exposing a database constraint error.

## Club duties on publication
Publishing a schedule now asks the clubs for officials itself, so a published
match day no longer waits for someone to run the wizard. For every published,
fixture-backed match the rule set decides what is needed: **Referees required
per match** (0 means nothing is requested) gives the number of roles, taken in
the wizard's order (head, assistant 1, assistant 2, fourth, table). The missing
roles become open club duties, allocated with the same fair-load, non-playing-
club-first rules as **Auto-assign Club Duties**; existing referee assignments
and duties satisfy their role and are never duplicated. Matches linked to a
publication later (placeholder fixtures) get their duties when they are linked.

A rule set can opt out with **Ask clubs for officials on publication** when
officials are assigned by the federation only. Publication is never blocked by
officiating: if duties cannot be created (for example no other club can cover a
match) the reason is written on the match day and the wizard remains available.
Duties are not created retroactively for schedules published earlier.
