# Native accounting bridge
Candidate implementation. Requires native `account_payment`, with the provider addon
and credentials configured separately. No webhook or independent ledger is added.

Confirmed positive charges create one draft `account.move` under a locked event.
The selected product owns income accounts and tax defaults. Amount is the line unit
price, not a promised tax-inclusive total; finance must verify the resulting invoice
before posting. Club/federation charge ownership is separate from invoice company.
The payer is the invoice partner, never inferred from a guardian relationship.

Native invoice portal checkout, payment transactions, reconciliation, credit notes
and cancellation remain authoritative. Balance and payment state are related fields.
An invoiced event cannot settle until its posted invoice is paid. Non-invoiced legacy
events retain the existing handoff workflow. This does not certify provider sandbox
callbacks, partial payments, refunds, multi-company rules or live reconciliation.
