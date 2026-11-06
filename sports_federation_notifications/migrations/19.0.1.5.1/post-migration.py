"""Link existing actionable delivery evidence without replaying historical mail."""


def migrate(cr, version):
    cr.execute("""
        UPDATE federation_notification_log AS log
           SET mail_id = delivery.mail_id,
               queued_on = COALESCE(log.queued_on, mail.create_date),
               outbox_checked_on = COALESCE(log.outbox_checked_on, NOW())
          FROM federation_communication_delivery AS delivery
          JOIN mail_mail AS mail ON mail.id = delivery.mail_id
         WHERE delivery.log_id = log.id
           AND log.mail_id IS NULL
    """)
