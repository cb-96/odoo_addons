# Native accounting bridge

Optional addon; it is not installed by `sports_federation_app`. Requires native
`account_payment`, with the payment-provider addon and credentials configured
separately. No webhook or independent ledger is added.

Confirmed positive charges create one draft `account.move` under a locked event.
The selected product owns income accounts and tax defaults. Amount is the line unit
price, not a promised tax-inclusive total; finance must verify the resulting invoice
before posting. Club/federation charge ownership is separate from invoice company.
The payer is the invoice partner, never inferred from a guardian relationship.

Native invoice portal checkout, payment transactions, reconciliation, credit notes
and cancellation remain authoritative. Balance and payment state are related fields.
An invoiced event cannot settle until its posted invoice is paid. Non-invoiced legacy
events retain the existing handoff workflow.

Provider sandbox callbacks, partial payments, refunds, multi-company rules and
live reconciliation are not yet runtime-qualified; see the
[roadmap](../docs/roadmap.md#known-gaps) and the
[platform hardening acceptance suite](../docs/release/acceptance/platform-hardening.md).

## Club invoices in the portal

Whole-club representatives see **Invoices** on the club overview, with a badge
for unpaid invoices, and the list at `/my/club-invoices`: posted invoices of
charges owned by their clubs (`charge_owner = club`). **View and pay** opens
Odoo's invoice page through its access link, where the club can download the
invoice and pay online with the configured payment providers. Team-only
representatives do not see club invoices. This addon depends on
`sports_federation_portal` for the portal pages.
