# Sports Federation Officiating

Version: 19.0.1.6.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
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
