"""Process-local tokens for destructive cross-addon workflows.

The token object cannot be supplied by an HTTP or RPC client because identity,
not a serializable value, grants access. The context-key constant prevents
consumers from inventing compatible-looking bypass keys.
"""

MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY = "matchday_destructive_delete_token"
MATCHDAY_DESTRUCTIVE_DELETE_TOKEN = object()
