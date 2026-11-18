# Plan club duties with a gameday schedule

Upgrade `sports_federation_scheduling` to `19.0.3.11.0` and `sports_federation_officiating` to `19.0.3.3.0` after deploying this change.
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
- **Create governed duty run** is the persisted draft-only path. It stores the
  exact proposal from `federation.schedule.club.duty.review`, rejects changed
  schedule geometry, capacity, pins, existing duties or officials, and can
  restore the previous draft policy and plan while no later change intervened.
- On a current published schedule, **Plan club duties** remains the intentionally
  immediate additive workflow: applying creates only missing open duties and
  notifies clubs. Published duties are not presented as rollback-safe planning.
- Avoiding clubs playing concurrently is enabled by default. Playing-club fallback
  is disabled by default and must be explicitly enabled; fallback is visible.
- One selected club supplies all missing roles for a fixture. Workload counts roles
  and duty minutes. Simultaneous capacity, qualified roles and buffers come from the
  club's season capacity policy; individual eligibility and availability remain
  separate.
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

## Season-fair allocation

Give a club's capacity policy a **Season Target Minutes** value to state the
duty minutes that club should carry over the season. When a club in the season
has a target, the review refines the feasible allocation toward the targets:

- The season ledger counts the minutes of every club duty that is not rejected
  on matches published from schedules of the same season, using each match's
  operational slot, or its published slot.
- Only clubs with a target receive moved duties. Pins, opponents, qualified
  roles, simultaneous capacity with preparation, rest and travel buffers, and
  the playing-club policy stay hard constraints. A move or swap is kept only
  when it lowers fallback duties first, then the squared deviation from the
  targets, then the number of changed fixtures, so results are reproducible.
- The review shows, per club, the season so far, the minutes planned now, the
  projection, the target and the deviation. Governed club-duty runs keep the
  same balance in their summary.
- Changing a target marks reviewed draft plans for review again; publication
  is refused until they are reviewed. An open review must be refreshed before
  it can be applied when the ledger changed in the meantime.
- Balancing runs only on an allocation without blocking issues.
- A capacity policy without any qualified role qualifies the club for no role.
  A club without a capacity policy remains unrestricted.
