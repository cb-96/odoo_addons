from odoo.exceptions import AccessError
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


@tagged("post_install", "-at_install", "sf_portal_create_fields")
class TestPortalWriteFields(TransactionCase):
    """Portal writes are deny-by-default per model and field."""

    def test_every_write_allowlisted_field_exists(self):
        policy = self.env["federation.portal.privilege"].PORTAL_WRITE_FIELDS
        for model_name, field_names in policy.items():
            if model_name not in self.env:
                continue
            with self.subTest(model=model_name):
                self.assertFalse(
                    sorted(set(field_names) - set(self.env[model_name]._fields)),
                    "Unknown fields in the portal write allowlist.",
                )

    def test_unlisted_model_and_field_are_refused_before_any_write(self):
        Privilege = self.env["federation.portal.privilege"]
        club = self.env["federation.club"].create({"name": "Write Policy Club"})
        team = self.env["federation.team"].create(
            {"name": "Write Policy Team", "club_id": club.id}
        )
        with self.assertRaisesRegex(AccessError, "not allowed for this model"):
            Privilege.portal_write(
                team, {"name": "Renamed"}, scope_domain=[("id", "=", team.id)]
            )
        season = self.env["federation.season"].create(
            {
                "name": "Write Policy Season",
                "code": "WPS",
                "date_start": "2090-01-01",
                "date_end": "2090-12-31",
            }
        )
        roster = self.env["federation.team.roster"].create(
            {"team_id": team.id, "season_id": season.id}
        )
        with self.assertRaisesRegex(AccessError, "unsupported fields: status"):
            Privilege.portal_write(
                roster,
                {"notes": "ok", "status": "active"},
                scope_domain=[("id", "=", roster.id)],
            )
        self.assertEqual(roster.status, "draft")
        self.assertFalse(roster.notes)
