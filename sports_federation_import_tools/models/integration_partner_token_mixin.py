import base64
import hashlib
import hmac
import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationIntegrationPartnerTokenMixin(models.AbstractModel):
    _name = "federation.integration.partner.token.mixin"
    _description = "Federation Integration Partner Token Helpers"

    @api.model
    def _generate_auth_token(self):
        """Return a new raw integration token."""
        return secrets.token_urlsafe(24)

    @api.model
    def _auth_token_is_hashed(self, stored_token):
        """Return whether a stored token already uses the hash format."""
        return bool(
            stored_token and stored_token.startswith(f"{self.TOKEN_HASH_PREFIX}$")
        )

    @api.model
    def _hash_auth_token(self, token, salt=None, rounds=None):
        """Hash a raw token before persisting it."""
        if not token:
            raise ValidationError("Integration tokens cannot be empty.")
        salt = salt or secrets.token_hex(self.TOKEN_SALT_BYTES)
        rounds = rounds or self.TOKEN_HASH_ROUNDS
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            token.encode("utf-8"),
            salt.encode("utf-8"),
            rounds,
        )
        encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
        return f"{self.TOKEN_HASH_PREFIX}${rounds}${salt}${encoded_digest}"

    @api.model
    def _verify_stored_auth_token(self, stored_token, candidate_token):
        """Verify a candidate token against the stored representation."""
        if not stored_token or not candidate_token:
            return False
        if not self._auth_token_is_hashed(stored_token):
            return hmac.compare_digest(stored_token, candidate_token)

        try:
            _prefix, rounds, salt, encoded_digest = stored_token.split("$", 3)
            rounds = int(rounds)
        except (TypeError, ValueError):
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            candidate_token.encode("utf-8"),
            salt.encode("utf-8"),
            rounds,
        )
        candidate_digest = base64.urlsafe_b64encode(digest).decode("ascii")
        return hmac.compare_digest(candidate_digest, encoded_digest)

    @api.model
    def _prepare_auth_token_values(
        self, token, rotation_required=False, mark_rotated=True
    ):
        """Build storage values for a raw token."""
        values = {
            "auth_token": self._hash_auth_token(token),
            "auth_token_last4": token[-4:] if len(token) >= 4 else token,
            "token_rotation_required": rotation_required,
        }
        if mark_rotated:
            values["token_last_rotated_on"] = fields.Datetime.now()
        return values

    def _issue_auth_token(self, rotation_required=False):
        """Generate, hash, persist, and return a new raw token."""
        self.ensure_one()
        raw_token = self._generate_auth_token()
        self.write(
            self._prepare_auth_token_values(
                raw_token,
                rotation_required=rotation_required,
                mark_rotated=True,
            )
        )
        return raw_token

    @api.model
    def _migrate_plaintext_tokens(self):
        """Hash legacy plaintext tokens and flag them for scheduled rotation."""
        partners = (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("auth_token", "!=", False),
                ]
            )
        )
        for partner in partners:
            if partner._auth_token_is_hashed(partner.auth_token):
                continue
            partner.write(
                partner._prepare_auth_token_values(
                    partner.auth_token,
                    rotation_required=True,
                    mark_rotated=False,
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        """Hash any raw token values before new partner records are created."""
        prepared_vals_list = []
        for vals in vals_list:
            prepared_vals = dict(vals)
            raw_token = prepared_vals.get("auth_token")
            if raw_token and not self._auth_token_is_hashed(raw_token):
                prepared_vals.update(
                    self._prepare_auth_token_values(
                        raw_token,
                        rotation_required=bool(
                            prepared_vals.get("token_rotation_required", False)
                        ),
                        mark_rotated=True,
                    )
                )
            prepared_vals_list.append(prepared_vals)
        return super().create(prepared_vals_list)

    def write(self, vals):
        """Hash any raw token values before they are persisted."""
        prepared_vals = dict(vals)
        raw_token = prepared_vals.get("auth_token")
        if raw_token and not self._auth_token_is_hashed(raw_token):
            prepared_vals.update(
                self._prepare_auth_token_values(
                    raw_token,
                    rotation_required=bool(
                        prepared_vals.get("token_rotation_required", False)
                    ),
                    mark_rotated=True,
                )
            )
        return super().write(prepared_vals)
