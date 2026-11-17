"""Process-local token for writes to published match planning.

Kickoff, location and publication pointers of a published match belong to the
schedule. Only the publication handoff and audited match-day commands may change
them. The token is an object, so an HTTP or RPC client cannot supply it; the
context-key constant keeps every trusted caller on the same key.
"""

PUBLISHED_PLANNING_CONTEXT_KEY = "publication_handoff_token"
PUBLISHED_PLANNING_TOKEN = object()


def with_published_planning_token(records):
    """Return ``records`` allowed to write published match planning fields."""
    return records.with_context(
        **{PUBLISHED_PLANNING_CONTEXT_KEY: PUBLISHED_PLANNING_TOKEN}
    )
