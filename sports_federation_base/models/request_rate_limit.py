from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationRequestRateLimit(models.Model):
    _name = "federation.request.rate.limit"
    _description = "Federation Request Rate Limit Bucket"
    _order = "last_seen desc, id desc"

    _scope_subject_window_unique = models.Constraint(
        "unique(scope, subject, window_start)",
        "Rate-limit buckets must be unique per scope, subject, and window.",
    )

    scope = fields.Char(required=True, index=True)
    subject = fields.Char(required=True, index=True)
    window_start = fields.Datetime(required=True, index=True)
    hit_count = fields.Integer(required=True, default=1)
    last_seen = fields.Datetime(required=True, default=fields.Datetime.now, index=True)

    _POLICIES = {
        "public_competitions_json": {"limit": 30, "window_seconds": 60},
        "public_competition_feed": {"limit": 60, "window_seconds": 60},
        "public_team_feed": {"limit": 60, "window_seconds": 60},
        "integration_contracts": {"limit": 20, "window_seconds": 60},
        "integration_finance_events": {"limit": 20, "window_seconds": 60},
        "integration_inbound_deliveries": {"limit": 20, "window_seconds": 60},
    }

    @api.model
    def _get_now(self):
        return datetime.utcnow().replace(microsecond=0)

    @api.model
    def _get_window_start(self, now, window_seconds):
        epoch = datetime(1970, 1, 1)
        window_epoch = (
            int((now - epoch).total_seconds() // window_seconds) * window_seconds
        )
        return epoch + timedelta(seconds=window_epoch)

    @api.model
    def _get_policy_param_name(self, scope, field_name):
        return f"sports_federation.rate_limit.{scope}.{field_name}"

    @api.model
    def _get_policy(self, scope):
        policy = self._POLICIES.get(scope)
        if not policy:
            raise ValidationError("The selected rate-limit policy is not available.")

        config = self.env["ir.config_parameter"].sudo()
        limit = int(
            config.get_param(
                self._get_policy_param_name(scope, "limit"),
                policy["limit"],
            )
        )
        window_seconds = int(
            config.get_param(
                self._get_policy_param_name(scope, "window_seconds"),
                policy["window_seconds"],
            )
        )
        if limit < 1 or window_seconds < 1:
            raise ValidationError(
                "Rate-limit policies must use positive limits and windows."
            )
        return {
            "limit": limit,
            "window_seconds": window_seconds,
        }

    @api.model
    def consume(self, scope, subject):
        policy = self._get_policy(scope)
        now = self._get_now()
        window_start = self._get_window_start(now, policy["window_seconds"])
        subject = (subject or "").strip() or "ip:unknown"

        bucket = self.search(
            [
                ("scope", "=", scope),
                ("subject", "=", subject),
                ("window_start", "=", window_start),
            ],
            limit=1,
        )
        if bucket:
            hit_count = bucket.hit_count + 1
            bucket.write(
                {
                    "hit_count": hit_count,
                    "last_seen": now,
                }
            )
        else:
            hit_count = 1
            bucket = self.create(
                {
                    "scope": scope,
                    "subject": subject,
                    "window_start": window_start,
                    "hit_count": hit_count,
                    "last_seen": now,
                }
            )

        retry_after = 0
        if hit_count > policy["limit"]:
            elapsed = int((now - window_start).total_seconds())
            retry_after = max(policy["window_seconds"] - elapsed, 1)

        return {
            "allowed": hit_count <= policy["limit"],
            "limit": policy["limit"],
            "remaining": max(policy["limit"] - hit_count, 0),
            "retry_after": retry_after,
            "subject": subject,
            "scope": scope,
            "window_start": window_start,
            "bucket_id": bucket.id,
        }
