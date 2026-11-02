from uuid import uuid4
from odoo import api, SUPERUSER_ID
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'sf_release_confidence')
class TestJobClaiming(TransactionCase):
    def test_two_cursors_cannot_claim_one_job(self):
        job_id = None
        try:
            with self.registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                job = env['federation.operation.job'].create({'name': 'Claim exclusion',
                    'source_model': 'res.partner', 'source_res_id': env.ref('base.main_partner').id,
                    'correlation_id': 'claim-' + uuid4().hex})
                job_id = job.id
                cr.commit()
            with self.registry.cursor() as first, self.registry.cursor() as second:
                a = api.Environment(first, SUPERUSER_ID, {})['federation.operation.job'].browse(job_id)
                b = api.Environment(second, SUPERUSER_ID, {})['federation.operation.job'].browse(job_id)
                self.assertTrue(a._claim())
                self.assertFalse(b._claim())
                first.rollback()
                second.rollback()
        finally:
            if job_id:
                with self.registry.cursor() as cr:
                    api.Environment(cr, SUPERUSER_ID, {})['federation.operation.job'].browse(job_id).unlink()
                    cr.commit()
