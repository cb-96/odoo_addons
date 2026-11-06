# Member and family services

Optional addon; it is not installed by `sports_federation_app`. Runtime,
browser and human acceptance are still open; see the
[member lifecycle acceptance suite](../docs/release/acceptance/member-lifecycle.md).

`/my/family` separates named people and requires explicit subject confirmation for
renewal, document, licence and lifecycle requests. Members and verified guardians
see personal records; current club representatives can request membership changes
only for linked players in their own club. Club status never grants guardian-only
document access. Payer status never grants personal document access.

Renewal reuses one later-season draft and copies requirements, not evidence or
approval. Federation activation checks current required evidence and records a
review reason. Membership, licence, invoice payment and sporting eligibility remain
separate. Missing licences can be requested as drafts; federation activation stays
in the existing licence workflow. Eligibility summaries use the existing roster
engine and never claim universal eligibility without a competition context.

Guardian claims use a private, rotatable person reference and independently reviewed
relationship evidence. Only verified, dated relationships grant access. Current
scope is checked again on every upload, download and mutation. No-store responses
avoid persistent browser caches; already seen information cannot be recalled.

Reviewed identity dialogs link existing partners, preview effects and reject stale
snapshots. Non-overlapping service history can be consolidated without deleting
player, licence or result history. Duplicate players are retired, duplicate-person
delegations revoked and moved evidence returned for review. Active duplicate login
accounts and overlapping memberships block consolidation rather than being merged
silently. New complete name/date matching scenarios use a normalised unique key;
legacy records are not auto-linked. Email is never identity evidence.

Evidence revisions are retained as immutable, company-scoped reviewer records.
Parental-purpose uploads create a draft in the owning parental-approval workflow;
generic membership review cannot verify parental approval. Payment summaries expose
native invoice balances only to an authorised invoice partner when the optional
native-accounting bridge is installed and a finance event is explicitly linked.

Cancellation, reactivation and membership transfer require federation decisions
against a source revision. Reactivation and destination membership return to draft
review. These commands do not change player clubs, licences, rosters or invoices;
those actions remain with their sporting and finance owners.

The [member lifecycle acceptance suite](../docs/release/acceptance/member-lifecycle.md)
describes installation, validation, role ownership, matching boundaries,
retention qualification and acceptance metrics.
