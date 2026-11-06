"""Mark only mail explicitly linked to federation notification evidence.

No mail is sent, recreated or deleted. Historical unlinked mail is not inferred.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE mail_mail AS mail
           SET federation_notification_owned = TRUE
         WHERE federation_notification_owned IS NOT TRUE
           AND (EXISTS (SELECT 1 FROM federation_notification_log AS log
                        WHERE log.mail_id = mail.id)
                OR EXISTS (SELECT 1 FROM federation_communication_delivery AS delivery
                           WHERE delivery.mail_id = mail.id))
    """)
    cr.execute("""
        CREATE INDEX IF NOT EXISTS federation_receipt_recipient_cursor_idx
            ON federation_communication_receipt (recipient_id, id DESC)
            WHERE superseded_on IS NULL
    """)
