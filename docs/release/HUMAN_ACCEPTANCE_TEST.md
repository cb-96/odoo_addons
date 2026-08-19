# Human Acceptance Test for Release Candidate

## 1. Purpose

Validate the complete federation workflow with realistic roles, data, devices, and recovery scenarios before tagging RC1.

## 2. Participants

Assign separate people where practical:

- Release coordinator
- Federation administrator
- Tournament manager
- Club representative A
- Club representative B from another club
- Referee or officiating coordinator
- Result validator
- Result approver
- Observer taking notes and evidence

## 3. Preparation

1. Deploy the exact candidate commit to a disposable production-like environment.
2. Restore an anonymized recent database or create representative test data.
3. Configure outbound email to a safe test inbox.
4. Enable the same reverse proxy, workers, timeout, attachment, and database settings planned for production.
5. Create two clubs, at least eight teams, twelve players per team, four courts, two gamedays, and user accounts for every role.
6. Record the commit SHA, database snapshot identifier, browser versions, start time, and participants.
7. Confirm a restore point exists before testing.
8. Open a defect log with severity, reproduction steps, evidence, owner, and disposition columns.

## 4. Entry criteria

- RC CI workflow is green.
- Database upgrade completed without unresolved warnings.
- No critical or high defect is open.
- Test users can sign in and their role memberships are verified.
- Email delivery and system time are correct.

## 5. Test sequence

### A. Competition and rules setup

1. Administrator creates a season, competition edition, rule set, and division.
2. Configure scoring, tie-breaks, squad limits, qualification, and required officials.
3. Lock the rule set.
4. Attempt to change locked scoring values. Expected: change is blocked.
5. Duplicate the rules for a future version. Expected: historical configuration remains unchanged.
6. Open the tournament. Expected: competition identity and effective rules can no longer change silently.

### B. Club portal isolation

1. Club A representative signs in on desktop.
2. Create or update Club A teams, contacts, registration, and roster.
3. Club B representative performs the same actions for Club B.
4. Manually substitute a Club B record ID in a Club A URL or request.
5. Expected: access is denied without revealing Club B data.
6. Repeat one registration and roster workflow on a mobile viewport.
7. Sign out, expire a session, and retry a pending action. Expected: safe recovery without duplicate submission.

### C. Stage and progression builder

1. Manager creates a group phase followed by knockout and placement stages.
2. Create groups, rounds, and progression mappings.
3. Attempt a self-referencing or cyclic progression. Expected: blocked.
4. Preview deletion of an unused stage. Expected: dependencies are listed accurately.
5. Attempt deletion of a stage with matches. Expected: explicit warning or block according to policy.
6. Confirm rollback leaves the original structure intact when deletion is cancelled.

### D. Gamedays and schedule planning

1. Create one shared gameday for two divisions.
2. Generate slots across four courts with a planned break.
3. Assign fixed matches manually.
4. Run auto-schedule preview and compare warnings with the planner.
5. Execute scheduling and inspect rest time, court conflicts, duplicate matches, and unscheduled matches.
6. Open the planner as a second manager.
7. Manager A moves a match. Manager B submits an action from the stale screen.
8. Expected: Manager B receives a clear stale-revision conflict and Manager A's change remains.
9. Test undo and redo after a normal assignment.
10. Attempt to assign two matches to the same slot. Expected: one assignment only.

### E. Validation and publication

1. Validate the completed gameday.
2. Change one assignment after validation.
3. Attempt publication. Expected: rejected because validation is stale.
4. Validate again and publish.
5. Confirm the published schedule is visible to the correct portal users.
6. Republish with an override reason where policy permits warnings.
7. Confirm hard blockers cannot be bypassed by a reason.

### F. Officiating

1. Assign a qualified referee and confirm the duty.
2. Attempt to complete an unconfirmed assignment. Expected: blocked.
3. Create an overlapping assignment. Expected: conflict or explicit warning according to policy.
4. Confirm the portal user can see only their own duty.
5. Complete the confirmed duty and verify timestamps and audit history.

### G. Results and standings

1. Enter results through the intended portal or operator workflow.
2. Submit, verify, and approve with three distinct users.
3. Expected: submitter cannot verify or approve their own result.
4. Confirm approved results appear in official standings.
5. Attempt direct reset of an approved result. Expected: blocked.
6. Contest and correct the result through the audited workflow.
7. Reapprove and verify standings and knockout progression recalculate correctly.

### H. Notifications and operational queues

1. Trigger registration, publication, referee, and result notifications.
2. Confirm recipients, language, links, and duplicate prevention.
3. Simulate a recoverable delivery failure.
4. Acknowledge and retry it through the operator workflow.
5. Confirm the operational queue exposes actionable failures without leaking sensitive information.

### I. Recovery and resilience

1. Take a database backup after publication.
2. Perform a controlled application restart during a non-destructive workflow.
3. Confirm users recover without duplicate writes.
4. Restore the backup to a separate environment.
5. Verify competition, schedule, assignments, results, audits, and attachments.
6. Execute the documented rollback procedure for the candidate build.

## 6. Evidence to collect

- Screenshots of each major workflow and expected block
- CI run URL and commit SHA
- Database migration and restore logs
- Email samples with personal data removed
- Conflict and access-denied responses
- Final standings and bracket export
- Defect log with disposition
- Signed approval record

## 7. Severity and exit criteria

- **Critical**: data loss, privilege escape, incorrect official outcome, unrecoverable deployment. RC is blocked.
- **High**: core workflow unavailable, duplicate schedule, broken progression, migration failure. RC is blocked.
- **Medium**: workaround exists but materially harms operations. Release owner decides with documented acceptance.
- **Low**: cosmetic or minor usability issue. May be deferred.

Pass only when all mandatory scenarios are completed, no critical or high defects remain, restore and rollback succeed, and every required approver signs the release ticket.
