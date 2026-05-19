# Sports Federation Notifications

Centralised notification helpers, email templates, and scheduled reminders.
Provides a reusable service layer for sending emails and creating activities,
with a log of all notifications sent.

## Purpose

Gives other modules a **single entry point** for sending notifications. Instead
of each module implementing its own mail logic, they call the notification
service, which handles template rendering, activity creation, sending, and logging.

## Dependencies

| Module | Reason |
|--------|--------|
| `sports_federation_base` | Core entities, federation manager group resolution |
| `sports_federation_people` | Player and referee contact resolution |
| `sports_federation_tournament` | Tournament, participant, and match event sources |
| `sports_federation_portal` | Season-registration confirmation and rejection hooks |
| `sports_federation_public_site` | Tournament publication trigger |
| `sports_federation_result_control` | Result submission, approval, and contest triggers |
| `sports_federation_standings` | Standing freeze trigger |
| `sports_federation_finance_bridge` | Finance confirmation trigger |
| `sports_federation_officiating` | Referee assignment and staffing alert triggers |
| `mail` | Email engine and mail.activity support |

## Models

### `federation.notification.log`

Audit record of every notification sent through the federation.

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Notification title |
| `target_model` / `target_res_id` | Char / Integer | What record triggered it |
| `recipient_partner_id` | Many2one | Recipient partner |
| `recipient_email` | Char | Recipient email address |
| `notification_type` | Selection | email / activity / other |
| `template_xmlid` | Char | Which template was used |
| `sent_on` | Datetime | When sent |
| `state` | Selection | pending / sent / failed |
| `message` | Text | Content or error details |

### `federation.notification.service` (AbstractModel)

Reusable service methods callable by any module.

| Method | Description |
|--------|-------------|
| `send_email_template(record, template_xmlid, ...)` | Send an email using a mail.template and log it |
| `create_activity(record, activity_type_xmlid, ...)` | Create a mail.activity and log it |
| `_cron_placeholder_notification_scan()` | Scheduled scan for overdue registrations and officiating gaps |

## Data Files

| File | Content |
|------|---------|
| `data/mail_templates.xml` | Generic contact, registration, publication, result, standings, finance, and referee assignment templates |
| `data/ir_cron.xml` | Daily notification scan plus daily notification-log retention cleanup |

## Key Behaviours

1. **Service pattern** — AbstractModel with helper methods; no table, just logic.
2. **Comprehensive logging** — Every send/activity creation produces a log entry.
3. **Multi-recipient email delivery** — `send_email_template()` accepts a single email or a collection of emails and deduplicates them before sending.
4. **QWeb templates** — Email templates use Odoo 19 QWeb syntax (`<t t-out=""/>`).
5. **Live workflow coverage** — Season registration confirmation/rejection, tournament publication, participant confirmation, result approval/contest, standing freeze, finance confirmation, referee assignment, and suspension activation all dispatch concrete emails or direct mail deliveries.
6. **Activity-based operational follow-up** — Result submission creates verifier activities, while overdue referee confirmations and officiating shortages create federation-manager activities.
7. **Scheduled scan** — Cron logs stale draft registration reminders and triggers the officiating follow-up activities above.
8. **Failure visibility without transaction rollback** — Missing recipients or template failures create `failed` notification logs instead of blocking the business workflow.
9. **Suspension delivery fallback** — `send_suspension_issued()` now sends a direct email and logs the outcome even when no dedicated mail template exists yet.
10. **Retention cleanup** — Notification logs are purged automatically after their state-specific retention windows in `DATA_RETENTION_POLICY.md` expire.

## Integration configuration (env)

The notification service and mail templates assume an external mail delivery configuration managed by the Odoo instance (SMTP or provider API). Do not hardcode credentials in code or data files. Recommended practice:

- Store runtime credentials in environment variables and/or CI secret stores.
- Use `ci/integrations.env.example` as a template for common variables (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SENDGRID_API_KEY, etc.).
- Keep real `.env` files out of source control (the repository `.gitignore` already excludes `.env` and `ci/.env`).

To apply values to Odoo system parameters you can either configure them via the Odoo Settings UI or set `ir.config_parameter` entries using an Odoo shell script or the admin UI.

