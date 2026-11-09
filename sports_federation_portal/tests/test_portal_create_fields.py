from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_portal_create_fields")
class TestPortalCreateFields(TransactionCase):
    """The portal create allowlist names only fields that exist."""

    def test_every_allowlisted_field_exists(self):
        policy = self.env["federation.portal.privilege"].PORTAL_CREATE_FIELDS
        for model_name, field_names in policy.items():
            if model_name not in self.env:
                continue
            model = self.env[model_name]
            with self.subTest(model=model_name):
                self.assertFalse(
                    sorted(set(field_names) - set(model._fields)),
                    "Unknown fields in the portal create allowlist.",
                )

    def test_compliance_targets_can_be_created_from_the_portal(self):
        """Every portal compliance target field is allowlisted."""
        if "federation.document.requirement" not in self.env:
            return
        requirement = self.env["federation.document.requirement"]
        allowed = self.env["federation.portal.privilege"].PORTAL_CREATE_FIELDS[
            "federation.document.submission"
        ]
        for target_model in requirement.PORTAL_TARGET_MODELS:
            with self.subTest(target=target_model):
                self.assertIn(
                    requirement._portal_get_target_field_name(target_model), allowed
                )
