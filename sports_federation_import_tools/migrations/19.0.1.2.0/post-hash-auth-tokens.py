"""Post-migration: hash any remaining plaintext integration partner tokens.

The runtime ``_register_hook`` guard hashes tokens on every module load, but
this one-time migration script makes the hash migration explicit and version-
gated so that upgrade tooling can report it as a deliberate schema-level
change rather than a silent runtime side effect.

Any token that has not yet been hashed (i.e. does not start with the
``pbkdf2_sha256$`` prefix) is hashed and flagged for operator rotation.
Partners with no token are untouched.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_HASH_PREFIX = "pbkdf2_sha256$"


def migrate(cr, version):
    """Hash legacy plaintext auth tokens and flag them for rotation."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Partner = env["federation.integration.partner"]
    partners = (
        Partner.sudo()
        .with_context(active_test=False)
        .search(
            [
                ("auth_token", "!=", False),
            ]
        )
    )
    migrated = 0
    for partner in partners:
        if partner.auth_token and not partner.auth_token.startswith(_HASH_PREFIX):
            partner._prepare_auth_token_values(
                partner.auth_token,
                rotation_required=True,
                mark_rotated=False,
            )
            partner.write(
                partner._prepare_auth_token_values(
                    partner.auth_token,
                    rotation_required=True,
                    mark_rotated=False,
                )
            )
            migrated += 1
    if migrated:
        _logger.info(
            "Hashed %d plaintext integration partner token(s). "
            "Operators should rotate flagged tokens before the next partner authentication.",
            migrated,
        )
