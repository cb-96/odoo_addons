# Club season player registration

A season is the federation's annual administrative period. A competition edition
is one competition's run within that period. Season dates, licensing, roster
history, budgets, public discovery and reporting remain in place.

## Normal journey

1. Open the season in Administration. Configure the Season Player Registration Fee
   (`player_season_registration`) and optional category/gender fee schedules.
2. Club representatives open **Season players** from `/my/preparation`, choose
  their club and season, select players, and submit pending registrations. The
  detail page lists each season licence with its approval state and expiry date.
3. Set the club billing contact before approving positive-fee registrations.
   Federation managers review **Clubs & People > Season Player Registrations**.
   They can collect all current club players as drafts or add players individually.
4. Approve pending players. Each player's existing season licence is the canonical
   registration record; no parallel player identity or duplicate registration line
   is introduced. Approval activates that licence and creates one source-linked
   finance event for its annual fee.
5. Register teams in competitions normally. Team roster pickers only show approved
   players for that club and season. Server-side validation applies to imports,
   direct ORM writes, roster scope changes and live eligibility checks as well.
6. Set the club billing contact, review/confirm the finance events, and (with
   native accounting installed) set the registration product and choose **Create
   club player invoice**. This creates one draft invoice with one line per
   confirmed, positive, uninvoiced player charge. Top-ups create a separate draft
   invoice only for new charges. Posting, sending, payment collection and
   reconciliation remain explicit accounting actions.

A licence must be active and valid on the roster/match reference date. The rule is
mandatory even when the competition has no optional eligibility rule set. An
explicitly selected licence must match the same player, club and season.

## Billing and approval policy

- Annual player registration is charged once per licence, independent of how many
  competition teams the player joins. Repeated approval and top-ups do not charge
  previously registered players again.
- Approval, not invoice settlement, gates roster registration. A payment-first
  policy is not inferred. Existing invoice settlement/reconciliation remains the
  source of truth for payments.
- Fees default to zero until configured. A zero-valued fee schedule is intentional
  and is not replaced by the default amount. Configure prices before approval.
- Fees are snapshotted in finance events. Reapproval never reprices existing events.
- Cancelling registration removes eligibility, but does not silently erase charges
  or create refunds. Financial corrections use the existing credit/review workflow.
- Existing annual team enrolments remain as internal team participation records.
  They do not register players. Their separate fee is opt-in for new seasons via
  **Also Charge Annual Team Enrolment**. Existing seasons retain the previous team
  fee policy on upgrade; disable it explicitly when moving to player-only billing.
- Membership services, if installed, remain separate. Review their fee policy to
  avoid intentionally billing both membership and annual player participation.

## Top-ups and history

Adding new draft players and submitting them does not revoke already active player
licences. Only pending licences are activated on approval. Approved licence scope
cannot be changed or deleted. Cancel instead; transfers need an explicit governed
policy and are not implemented as a silent reassignment. Cancelled player records
remain reserved by the existing player/season uniqueness constraint.

## Upgrade

Upgrade base, people, tournament, registration, rosters, finance bridge, portal,
navigation, live workspace and native accounting (if installed) together. Existing licences are grouped into club
season registrations without changing their state or creating retrospective fees.
Existing club registration headers use the main company during migration; review
company ownership before new approvals if operating multiple companies.
Players without an active season licence are deliberately blocked from new roster
registration. Review existing rosters before qualification; this migration does
not fabricate approvals to make legacy data pass.

Seasons move to Administration; annual team enrolments are advanced records.
Competition creation defaults to the current open season, otherwise the next open
season, with an editable override. The board is labelled **Competition match board**;
its stable technical identifiers are retained. Annual planning targets, budgets,
reports and public season pages remain because they have legitimate annual uses.

## Qualification checklist

- Register a club's players, submit, approve, and invoice through the existing flow.
- Reject roster creation for missing, draft, expired, cancelled, wrong-club and
  wrong-season licences, including when no sport eligibility rule is configured.
- Confirm approved players remain eligible while a top-up is pending.
- Confirm two competition rosters do not create two annual player charges.
- Confirm repeated approval and zero-fee schedules are idempotent.
- Attempt forged club/player IDs and cross-club portal access; expect denial.
- Upgrade an existing database; verify licence states, invoices and fees are unchanged.
- Test cancelled registrations, season closure, roster history and live match checks.
