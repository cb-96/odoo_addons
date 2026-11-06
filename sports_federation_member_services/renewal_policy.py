"""Where is a renewal in its lifecycle, and what is it waiting for?

previous membership -> renewal initiated -> reused identity -> changed
information reviewed -> payment and compliance -> approved

Only the federation review, the verification of the required documents and the
use of the canonical identity gate approval; payment is shown for information
because the membership lifecycle deliberately keeps licence, payment and
sporting eligibility separate.
"""

STEPS = (
    ("none", "Not a renewal"),
    ("initiated", "Renewal initiated"),
    ("compliance", "Payment and compliance"),
    ("ready", "Ready to approve"),
    ("approved", "Approved"),
    ("cancelled", "Cancelled"),
)


def progress(
    is_renewal, state, has_review_note, unverified_documents, identity_current=True
):
    """Return ``(step, blockers)`` for one membership."""
    if not is_renewal:
        return "none", []
    if state == "cancelled":
        return "cancelled", []
    if state == "active":
        return "approved", []
    blockers = []
    if not identity_current:
        blockers.append(
            "This identity was merged. Renew the canonical identity instead."
        )
    if not has_review_note:
        blockers.append("Record the review of changed information.")
    if unverified_documents:
        blockers.append(
            "%s required %s still to verify."
            % (
                unverified_documents,
                "document is" if unverified_documents == 1 else "documents are",
            )
        )
    if not identity_current or not has_review_note:
        return "initiated", blockers
    if unverified_documents:
        return "compliance", blockers
    return "ready", blockers


def payment_note(finance_state):
    """Informational only: payment never blocks activation."""
    if not finance_state or finance_state == "settled":
        return False
    if finance_state == "cancelled":
        return "The linked finance charge was cancelled."
    return "Payment is outstanding. This does not block approval."
