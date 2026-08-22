# Release Candidate Approval Policy

An RC may be tagged only after all automated gates pass and the approvals below are recorded in the release ticket.

## Mandatory automated evidence

- Fresh installation of the V2 competition stack and affected integration addons
- Upgrade of all modules on the same database
- Complete V2 backend and portal suites
- Deterministic stage-graph, calendar-timeline, fairness, officiating,
  result-control, and notification contracts
- Static Python, XML, JavaScript, and whitespace checks
- No critical or high-severity security findings

## Required human approvals

1. **Technical owner**: confirms CI, migrations, rollback, repository state, and release notes.
2. **Tournament operations owner**: approves stage creation, scheduling, publication, corrections, and operational recovery.
3. **Club representative**: approves portal navigation, registrations, rosters, duties, and mobile usability.
4. **Security or governance reviewer**: approves portal privilege boundaries, access matrix, attachment policy, and audit trail.
5. **Data or process owner**: approves rules, standings, result correction, progression, and historical integrity.

The release owner must not self-approve every role. At minimum, technical and operational approval must come from different people.

## Automatic no-go conditions

- Failed or skipped mandatory CI lane
- Data loss, cross-club access, duplicate scheduling, incorrect standings, or incorrect progression
- Unrehearsed migration or rollback
- Open critical or high-severity defect
- Production configuration differs materially from the tested candidate
