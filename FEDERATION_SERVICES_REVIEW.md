# Verification and implementation candidate

Full requested scope is NOT complete. Do not deploy this candidate to production.
Baseline: workflow-improvement / 2cc4e84dcdcaae2407bff83bdf22ec2e2580d0d7.
This incremental patch preserves the committed live workspace and scheduling commands.

## Verification of points 1 to 5
1. Release automation and evidence gates exist. Staging install/upgrade, browser
   journeys, concurrent recovery, restoration and fallback have not been demonstrated.
2. Role tasks and preparation journeys exist. Helper/gate tests pass; five novice
   participants and real mobile/keyboard journeys have not been demonstrated.
3. Duty coverage addon and tests exist. Current ORM/browser acceptance is unverified.
4. Court operations and recovery implementation already exist in the current baseline.
   Their existing source is preserved; runtime acceptance remains unverified.
5. Visual planning and scheduling command hardening already exist in the baseline.
   They are not re-added or overwritten by this incremental patch.

## Candidate changes
- Preserves the existing court/visual workspace and scheduling command changes.
- Adds only the remaining member-services and native accounting candidate changes.
- Adds verified, dated guardian/payer relationships and company-scoped administration.
- Adds manager-controlled person/player identity links and multi-role season memberships.
- Adds draft renewal requests with prior-season continuity and duplicate renewal lookup.
- Adds /my/family and purpose-scoped uploads using the existing file policy/scanner.
  Uploaded is not verified; verification is independent and never grants eligibility.
  Payer status does not grant guardian access. Generic requests do not create existing
  parental-approval records or replace their owning workflow.
- Adds native invoice linkage for confirmed charges, row-locked invoice creation,
  authoritative invoice balances/payment states and unpaid-settlement bypass guards.
  Club/federation charge ownership is explicit. No parallel accounting ledger.
- Adds distinct-member and club membership retention comparisons, including unknown
  retention for an empty baseline. Membership is not proof of match participation.
- Adds five cohort helper tests and five Odoo personal-scope test definitions.

## Unfinished implementation, not merely unfinished validation
Point 6: identity backfill, duplicate detection/controlled merging, licence renewal,
parental-approval command linkage, verified request-recipient routing and full lifecycle.
Point 7 communication: complete deadline reminders/escalation, delivery deduplication,
failed-delivery administration, integrated notification centre and authenticated feeds.
Existing task digests and public calendars are preserved, not claimed as completion.
Point 7 payments: provider configuration and sandbox end-to-end integration, automatic
settlement and full failed/partial/refund/cancellation lifecycle. Native Accounting owns
these operations, but the new bridge has not been runtime-qualified.
Point 8: journey abandonment/time/intervention instrumentation, actual participant
retention and complete role-specific onboarding. Existing public team filters, display,
progression and calendars are preserved but not browser-requalified.
Cross-cutting accessibility, observability, short all-role guides and novice testing
remain open. Deferred product areas remain deferred.

## Validation scope
Patch applicability, source preservation, Python AST/XML parsing and focused helper
checks are recorded in the accompanying rebase validation report. Historical test
counts from the earlier candidate are not evidence for this rebased source.
Odoo ORM, registry, browser, accounting provider and concurrency tests still require
an installed staging runtime. This is not a runtime release certificate.

## Application
Use this replacement instead of the original federation_services_candidate.patch.
Do not apply both. It targets the supplied clean source at the baseline above.

```sh
git apply --check federation_services_current.patch
git apply federation_services_current.patch
```

On authorised staging install/upgrade sports_federation_app and run sf_member_services,
sf_live_workspace, sf_release_confidence and finance suites. Native account_payment
and the chosen provider addon are required. Configure invoice payer, company, product,
accounts and taxes before posting. Charge amount is the invoice line unit price;
finance must validate the resulting total and taxes. No provider credentials are supplied.
Complete the unfinished implementation and acceptance gates before production use.
