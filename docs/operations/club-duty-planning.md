# Plan club duties with a gameday schedule

Upgrade `sports_federation_officiating` to `19.0.2.2.0` after deploying this change.
Existing schedules without an explicit club-duty plan retain their rule-set-driven
publication behaviour. No production records are removed or automatically reassigned.

## Operator workflow

1. In Generate schedule, enable **Automatically plan club duties**.
2. Generate the draft schedules. A club-duty review opens against their actual slots.
3. Choose the official count. Zero uses each division's rule-set requirement.
4. Review fixture times, allocated clubs, roles, fallback indicators and club workloads.
5. Change the avoidance/fallback policy if needed, then **Refresh preview**.
6. Resolve every allocation issue and select **Apply club-duty plan**.
7. Review and publish the schedule through the normal approval workflow.
8. Publication creates open club duties and sends the existing club notifications.
9. Clubs nominate people; nomination linkage and individual official acceptance
   continue through the existing officiating workflow.

Draft schedules are persisted before the review dialog opens. Applying the review
persists club responsibilities on those drafts, not actionable nomination requests.
Closing the review does not undo schedule generation. The opted-in schedule remains
marked for review and cannot be published until its club-duty plan is applied.
Use **Review club duties** on the draft schedule to resume.

## Safety and limitations

- Allocation never selects either opponent's club.
- Avoiding clubs playing concurrently is enabled by default. Playing-club fallback
  is disabled by default and must be explicitly enabled; fallback is visible.
- One selected club supplies all missing roles for a fixture. Workload counts roles,
  not just matches. The allocator does not model the number of officials a club
  can supply concurrently; individual eligibility and availability remain separate.
- Existing duties and named assignments are preserved. Disabling preservation does
  not authorise destructive replacement: use Resolve / replace for existing records.
- Changes to draft slots, teams, rule requirements or coverage invalidate the review.
  Refresh and apply again. Stale opted-in plans block publication.
- Published duties show **Planning review required** when their match time or
  participating clubs change. Existing nominations are not silently replaced.
- Unresolved placeholder participants block allocation when officials are required.
  Resolve participants before applying that club-duty plan.
- Plans are stored per schedule. Amendments/copies do not inherit a reviewed plan;
  review the amendment explicitly. Existing duties are reconciled by fixture/role.
- These controls are available to federation managers. They do not grant new portal
  access or change who may accept an official assignment.

## Verification

Run the pure allocation tests:

```bash
python3 ci/test_club_duty_planning.py
```

Run the Odoo officiating tests in the isolated RC environment:

```bash
RC_CONFIDENCE_TEST_TAGS=sf_club_duty_planning scripts/ci/run_rc_validation.sh confidence
```

The database tests cover no premature duties, publication idempotency, stale
previews, slot changes, zero requirements, missing clubs and preserved officials.
Also exercise the UI end to end with a production-like restored database and rerun
release qualification on the resulting commit before deployment.

## Capacity, qualifications and manual pins

The reviewed allocator is shared by schedule validation and publication. A
club's season policy declares simultaneous headcount, qualified roles and
preparation, rest and travel buffers. A fixture may be pinned to one club with
a reason; recalculation preserves the pin and explains any capacity or
qualification conflict. Reviews show both role count and duty minutes. Current
published schedules use the same preview but create only missing duties and do
not alter match times.
