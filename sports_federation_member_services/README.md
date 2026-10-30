# Member and family services
Implementation candidate, not an acceptance certificate.

People are existing `res.partner` records; accounts remain `res.users`. The optional
player `person_id` is manager-controlled and unique. Memberships are season/club/role
records and do not replace licences, rosters or eligibility. No identity is inferred
from an email address. Existing players require reviewed identity linking.

Managers create and verify dated guardian or payer relationships. Only current
verified guardian relationships expand personal document and membership access.
Payer relationships never expand that access. Billing access remains native invoice
partner access. `/my/family` exposes bounded dictionaries, not elevated recordsets.

Requests use the shared upload policy and scanning configuration. Uploaded is not
verified. Verification is independent and applies only to the named purpose; it
never creates a parental approval or a licence. Existing parental approvals remain
in their owning workflow. Renewal creates/reuses a draft membership, preserving its
previous season reference; it does not activate membership or eligibility.

Remaining work: reviewed identity backfill, duplicate review/merge workflow, linked
parental-approval requests, notification routing, company-scoped administration,
full browser and concurrent transaction tests. No claim of complete point 6.
