# Integration env variables and how to apply them

Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

This repository standardises external-integration configuration (SMTP, OAuth, API keys, webhooks, S3) as environment variables.

Quick steps

1. Copy `ci/integrations.env.example` to `ci/.env` (or to a local `.env`) and fill values.
2. Keep `ci/.env` and any local `.env` files out of version control (the repo `.gitignore` already ignores them).
3. For CI, populate the same keys via your CI secret store or generate ephemeral values at runtime.

Applying values to Odoo

You can either configure the provider settings via the Odoo Settings UI or set system parameters programmatically. Example (run inside an `odoo shell` session):

```python
from os import environ
env['ir.config_parameter'].set_param('my_module.smtp_host', environ.get('SMTP_HOST') or '')
env['ir.config_parameter'].set_param('my_module.sendgrid_api_key', environ.get('SENDGRID_API_KEY') or '')
```

Replace `my_module.*` with the parameter keys your instance expects. Keep secrets in environment variables or secret stores and avoid committing them to Git.

Runtime keys written by CI helper
---------------------------------

When CI is run, the helper `ci/apply_env_to_ir_config.sh` (called from `ci/run_tests.sh`) will write non-empty integration environment variables into Odoo's `ir.config_parameter` table using the `integration.` prefix. The mapping is:

- `SMTP_HOST` → `integration.smtp_host`
- `SMTP_PORT` → `integration.smtp_port`
- `SMTP_USER` → `integration.smtp_user`
- `SMTP_PASSWORD` → `integration.smtp_password`
- `SMTP_USE_TLS` → `integration.smtp_use_tls`
- `EMAIL_FROM` → `integration.email_from`
- `SENDGRID_API_KEY` → `integration.sendgrid_api_key`
- `MAILGUN_API_KEY` → `integration.mailgun_api_key`
- `OAUTH_GOOGLE_CLIENT_ID` → `integration.oauth_google_client_id`
- `OAUTH_GOOGLE_CLIENT_SECRET` → `integration.oauth_google_client_secret`
- `OAUTH_GOOGLE_REDIRECT_URI` → `integration.oauth_google_redirect_uri`
- `OAUTH_GITHUB_CLIENT_ID` → `integration.oauth_github_client_id`
- `OAUTH_GITHUB_CLIENT_SECRET` → `integration.oauth_github_client_secret`
- `OAUTH_GITHUB_REDIRECT_URI` → `integration.oauth_github_redirect_uri`
- `TWILIO_ACCOUNT_SID` → `integration.twilio_account_sid`
- `TWILIO_AUTH_TOKEN` → `integration.twilio_auth_token`
- `SLACK_WEBHOOK_URL` → `integration.slack_webhook_url`
- `AWS_ACCESS_KEY_ID` → `integration.aws_access_key_id`
- `AWS_SECRET_ACCESS_KEY` → `integration.aws_secret_access_key`
- `S3_BUCKET` → `integration.s3_bucket`
- `S3_REGION` → `integration.s3_region`
- `ALLOWED_HOSTS` → `integration.allowed_hosts`

How modules should read these values
-----------------------------------

Prefer reading the values from `ir.config_parameter` inside Odoo; this lets CI inject values into the test DB for integration tests. Example usage in model/service code:

```python
from odoo import models
import os

class SomeService(models.AbstractModel):
	_name = 'my.module.service'

	def _get_smtp_host(self):
		# Prefer the stored system parameter written by CI
		param = self.env['ir.config_parameter'].sudo().get_param('integration.smtp_host')
		# Fallback to environment variable (useful in local dev)
		return param or os.environ.get('SMTP_HOST')
```

Notes:

- Values are written as strings; boolean flags like `SMTP_USE_TLS` may need parsing (`param == 'true'` or similar).
- Use `sudo()` when reading global parameters from code that might run in limited-permission contexts.
- Avoid logging secrets. Treat `integration.*` parameters as sensitive.

Optional upload malware scan hook
---------------------------------

Shared upload validation can call an external malware-scanning command before portal or
partner uploads are accepted. Configure it through these system parameters:

- `sports_federation.attachment_scan.command`
- `sports_federation.attachment_scan.timeout_seconds`

The configured command receives the raw upload bytes on stdin and these environment variables:

- `SF_ATTACHMENT_POLICY`
- `SF_ATTACHMENT_FILENAME`
- `SF_ATTACHMENT_MIMETYPE`

Exit code contract:

- `0`: upload is clean
- `10`: upload is infected and must be rejected
- any other non-zero code: verification failed and the upload is rejected with a retry-later message
