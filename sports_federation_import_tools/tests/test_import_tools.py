import base64
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sports_federation_import_tools.workflow_states import (
    IMPORT_JOB_STATE_SELECTION,
    INBOUND_DELIVERY_STATE_SELECTION,
    delivery_state_from_job_state,
)
from odoo.exceptions import AccessError
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestImportTools(TransactionCase):
    """Test cases for import tools wizards."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create test club
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TC001",
            }
        )
        # Create test tournament
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "code": "TT2024",
                "date_start": "2024-01-01",
                "date_end": "2024-01-31",
            }
        )
        # Create test team
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Test Team",
                "code": "TEAM001",
                "club_id": cls.club.id,
            }
        )

    def _create_csv_file(self, content):
        """Helper to create a CSV file binary."""
        return base64.b64encode(content.encode("utf-8"))

    def _approve_wizard_import(self, wizard):
        """Exercise approve wizard import."""
        wizard.dry_run = True
        wizard.action_parse_and_import()
        wizard.action_request_approval()
        wizard.action_approve_import()
        wizard.dry_run = False
        return wizard

    def _create_integration_partner(self, contract):
        """Exercise create integration partner."""
        partner = self.env["federation.integration.partner"].create(
            {
                "name": f"Partner {contract.code}",
                "code": f"PARTNER_{contract.code.upper()}",
            }
        )
        subscription = self.env["federation.integration.partner.contract"].create(
            {
                "partner_id": partner.id,
                "contract_id": contract.id,
            }
        )
        return partner, subscription

    def test_all_import_wizards_inherit_shared_mixin(self):
        """All managed import wizards should share the common mixin contract."""
        wizard_models = [
            "federation.import.clubs.wizard",
            "federation.import.seasons.wizard",
            "federation.import.teams.wizard",
            "federation.import.players.wizard",
            "federation.import.tournament.participants.wizard",
        ]

        for model_name in wizard_models:
            wizard_model = self.env[model_name]
            inherits = wizard_model._inherit
            if isinstance(inherits, str):
                inherits = [inherits]
            self.assertIn("federation.import.wizard.mixin", inherits)
            self.assertIn("template_id", wizard_model._fields)
            self.assertIn("mapping_guide", wizard_model._fields)
            self.assertTrue(hasattr(wizard_model, "_categorize_exception"))
            self.assertTrue(hasattr(wizard_model, "_finalize_import_result"))

    def test_import_wizard_mixin_composes_split_helpers(self):
        """The shared import wizard mixin should stay assembled from the focused helper mixins."""
        wizard_mixin = self.env["federation.import.wizard.mixin"]
        inherits = wizard_mixin._inherit
        if isinstance(inherits, str):
            inherits = [inherits]

        self.assertIn("federation.import.wizard.csv.mixin", inherits)
        self.assertIn("federation.import.wizard.governance.mixin", inherits)
        self.assertTrue(hasattr(wizard_mixin, "_get_csv_reader"))
        self.assertTrue(hasattr(wizard_mixin, "action_request_approval"))

    def test_import_job_uses_shared_state_selection(self):
        """Import job workflow states should come from the shared helper module."""
        self.assertEqual(
            self.env["federation.import.job"].STATE_SELECTION,
            IMPORT_JOB_STATE_SELECTION,
        )

    def test_inbound_delivery_uses_shared_state_selection(self):
        """Inbound delivery workflow states should come from the shared helper module."""
        self.assertEqual(
            self.env["federation.integration.delivery"].STATE_SELECTION,
            INBOUND_DELIVERY_STATE_SELECTION,
        )

    def test_inbound_delivery_model_composes_split_helpers(self):
        """The delivery model should stay assembled from the focused staging and lifecycle helpers."""
        delivery_model = self.env["federation.integration.delivery"]
        inherits = delivery_model._inherit
        if isinstance(inherits, str):
            inherits = [inherits]

        self.assertIn("federation.integration.delivery.stage.mixin", inherits)
        self.assertIn("federation.integration.delivery.workflow.mixin", inherits)
        self.assertIn("federation.integration.delivery.retention.mixin", inherits)
        self.assertTrue(hasattr(delivery_model, "stage_partner_delivery_result"))
        self.assertTrue(hasattr(delivery_model, "_purge_retained_deliveries"))

    def test_integration_partner_model_composes_split_helpers(self):
        """The partner model should stay assembled from focused token and rotation helpers."""
        partner_model = self.env["federation.integration.partner"]
        inherits = partner_model._inherit
        if isinstance(inherits, str):
            inherits = [inherits]

        self.assertIn("federation.integration.partner.token.mixin", inherits)
        self.assertIn("federation.integration.partner.rotation.mixin", inherits)
        self.assertTrue(hasattr(partner_model, "_hash_auth_token"))
        self.assertTrue(hasattr(partner_model, "action_rotate_token"))

    def test_shared_workflow_helper_maps_job_completion_to_delivery_state(self):
        """The shared workflow helper should map job completion states to delivery states."""
        self.assertEqual(delivery_state_from_job_state("completed"), "processed")
        self.assertEqual(
            delivery_state_from_job_state("completed_with_errors"),
            "processed_with_errors",
        )

    def test_import_wizard_mixin_categorizes_common_errors(self):
        """The shared mixin should keep the common error taxonomy stable across wizards."""
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": self._create_csv_file("name\nCategory Club"),
                "dry_run": True,
            }
        )

        self.assertEqual(
            wizard._categorize_exception(ValidationError("Club not found."))[0],
            "missing_reference",
        )
        self.assertEqual(
            wizard._categorize_exception(ValidationError("Club already exists."))[0],
            "duplicate_entry",
        )
        self.assertEqual(
            wizard._categorize_exception(ValidationError("Date format is invalid."))[0],
            "format_error",
        )
        self.assertEqual(
            wizard._categorize_exception(ValidationError("Name is required."))[0],
            "missing_required_field",
        )

    def test_import_wizard_mixin_executes_shared_row_create_flow(self):
        """The shared row-create helper should skip dry runs and record live failures consistently."""
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": self._create_csv_file("name\nRow Create Club"),
                "dry_run": True,
            }
        )

        dry_run_calls = []
        errors = []
        error_categories = {}
        self.assertTrue(
            wizard._execute_row_create(
                2,
                lambda: dry_run_calls.append("called"),
                errors,
                error_categories,
            )
        )
        self.assertEqual(dry_run_calls, [])
        self.assertEqual(errors, [])
        self.assertEqual(error_categories, {})

        wizard.dry_run = False
        self.assertFalse(
            wizard._execute_row_create(
                7,
                lambda: (_ for _ in ()).throw(ValidationError("Club already exists.")),
                errors,
                error_categories,
            )
        )
        self.assertEqual(error_categories["duplicate_entry"], 1)
        self.assertIn("Row 7 [duplicate_entry]: Club already exists.", errors)

    def test_import_clubs_dry_run_exposes_mapping_guide(self):
        """Clubs dry-run should validate rows without creating records and show guidance."""
        csv_content = (
            "name;code;email;phone;city\nNew Club;NC001;new@example.com;123456;City1"
        )
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": self._create_csv_file(csv_content),
                "dry_run": True,
            }
        )

        self.assertIn("Recommended columns", wizard.mapping_guide)

        wizard.action_parse_and_import()

        self.assertEqual(wizard.line_count, 1)
        self.assertEqual(wizard.success_count, 1)
        self.assertEqual(wizard.error_count, 0)
        self.assertTrue(wizard.template_id)
        self.assertFalse(
            self.env["federation.club"].search([("name", "=", "New Club")])
        )

    def test_import_governance_requires_approval_for_live_run(self):
        """Test that import governance requires approval for live run."""
        csv_content = "name;code;email;phone;city\nGoverned Club;GC001;gov@example.com;123456;City1"
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": self._create_csv_file(csv_content),
                "dry_run": True,
            }
        )

        wizard.action_parse_and_import()
        wizard.action_request_approval()

        self.assertTrue(wizard.governance_job_id)
        self.assertEqual(wizard.governance_job_id.state, "awaiting_approval")
        self.assertIn("Preview totals", wizard.governance_job_id.verification_summary)

        wizard.dry_run = False
        with self.assertRaises(ValidationError):
            wizard.action_parse_and_import()

        wizard.action_approve_import()
        self.assertEqual(wizard.governance_job_id.state, "approved")

        wizard.action_parse_and_import()

        self.assertEqual(wizard.governance_job_id.state, "completed")
        self.assertEqual(
            wizard.governance_job_id.pre_import_record_count + 1,
            wizard.governance_job_id.post_import_record_count,
        )
        self.assertIn(
            "Net new target records: 1", wizard.governance_job_id.verification_summary
        )
        self.assertTrue(
            self.env["federation.club"].search([("code", "=", "GC001")], limit=1)
        )

    def test_import_governance_invalidates_approval_when_file_changes(self):
        """Test that import governance invalidates approval when file changes."""
        initial_csv = "name;code\nInitial Club;IC001"
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": self._create_csv_file(initial_csv),
                "dry_run": True,
            }
        )

        wizard.action_parse_and_import()
        wizard.action_request_approval()
        wizard.action_approve_import()

        wizard.write(
            {
                "upload_file": self._create_csv_file("name;code\nChanged Club;CC001"),
                "dry_run": False,
            }
        )

        with self.assertRaises(ValidationError):
            wizard.action_parse_and_import()

    def test_partner_authentication_requires_subscription(self):
        """Test that partner authentication requires subscription."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_finance_event"
        )
        partner, subscription = self._create_integration_partner(contract)
        raw_token = partner._issue_auth_token()

        auth_partner, auth_subscription = self.env[
            "federation.integration.partner"
        ].authenticate_partner(
            partner.code,
            raw_token,
            contract_code=contract.code,
        )

        self.assertEqual(auth_partner, partner)
        self.assertEqual(auth_subscription, subscription)
        self.assertTrue(subscription.last_used_on)

        with self.assertRaises(AccessError):
            self.env["federation.integration.partner"].authenticate_partner(
                partner.code,
                "wrong-token",
                contract_code=contract.code,
            )

    def test_partner_token_rotation_hashes_storage_and_returns_usable_secret(self):
        """Token rotation should persist only the hash and return the raw secret once."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_finance_event"
        )
        partner, _subscription = self._create_integration_partner(contract)

        self.assertFalse(partner.auth_token)
        self.assertFalse(partner.auth_token_last4)

        action = partner.action_rotate_token()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        raw_token = wizard.issued_token

        partner.invalidate_recordset()

        self.assertTrue(raw_token)
        self.assertNotEqual(partner.auth_token, raw_token)
        self.assertTrue(partner.auth_token.startswith(f"{partner.TOKEN_HASH_PREFIX}$"))
        self.assertEqual(partner.auth_token_last4, raw_token[-4:])
        self.assertFalse(partner.token_rotation_required)

        auth_partner, _subscription = self.env[
            "federation.integration.partner"
        ].authenticate_partner(partner.code, raw_token)
        self.assertEqual(auth_partner, partner)

        audit_event = self.env["federation.audit.event"].search(
            [
                ("event_family", "=", "integration_token"),
                ("event_type", "=", "integration_token_rotated"),
                ("target_model", "=", "federation.integration.partner"),
                ("target_res_id", "=", partner.id),
            ],
            limit=1,
        )
        self.assertTrue(audit_event)
        self.assertEqual(audit_event.actor_user_id, self.env.user)
        self.assertEqual(audit_event.action_name, "action_rotate_token")
        self.assertIn("auth_token_last4", audit_event.changed_fields)

    def test_legacy_plaintext_tokens_are_migrated_and_flagged(self):
        """Legacy plaintext tokens should be hashed in place and marked for rotation."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_finance_event"
        )
        partner, _subscription = self._create_integration_partner(contract)
        legacy_token = "legacy-token-1234"

        self.env.cr.execute(
            """
            UPDATE federation_integration_partner
               SET auth_token = %s,
                   auth_token_last4 = NULL,
                   token_rotation_required = FALSE,
                   token_last_rotated_on = NULL
             WHERE id = %s
            """,
            [legacy_token, partner.id],
        )
        partner.invalidate_recordset()

        self.env["federation.integration.partner"]._migrate_plaintext_tokens()
        partner.invalidate_recordset()

        self.assertNotEqual(partner.auth_token, legacy_token)
        self.assertTrue(partner.auth_token.startswith(f"{partner.TOKEN_HASH_PREFIX}$"))
        self.assertEqual(partner.auth_token_last4, legacy_token[-4:])
        self.assertTrue(partner.token_rotation_required)

        auth_partner, _subscription = self.env[
            "federation.integration.partner"
        ].authenticate_partner(partner.code, legacy_token)
        self.assertEqual(auth_partner, partner)

    def test_inbound_delivery_stages_and_reuses_duplicate_payloads(self):
        """Test that inbound delivery stages and reuses duplicate payloads."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        payload = self._create_csv_file("name;code\nStaged Club;SC001").decode("utf-8")

        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=payload,
            source_reference="batch-001",
        )
        duplicate = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=payload,
            source_reference="batch-001",
        )

        self.assertEqual(delivery, duplicate)
        self.assertEqual(delivery.state, "staged")
        self.assertTrue(delivery.attachment_id)
        self.assertEqual(delivery.import_template_id, contract.import_template_id)

    def test_inbound_delivery_reuses_matching_idempotency_key(self):
        """Repeated deliveries with the same idempotency key should reuse the original record."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        payload = self._create_csv_file("name;code\nIdempotent Club;IDC001").decode(
            "utf-8"
        )

        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=payload,
            source_reference="batch-100",
            idempotency_key="delivery-001",
        )
        duplicate = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=payload,
            source_reference="batch-100",
            idempotency_key="delivery-001",
        )

        self.assertEqual(delivery, duplicate)
        self.assertEqual(delivery.idempotency_key, "delivery-001")
        self.assertTrue(delivery.idempotency_fingerprint)

    def test_inbound_delivery_rejects_conflicting_idempotency_key_reuse(self):
        """Reusing an idempotency key for a different request should fail fast."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        first_payload = self._create_csv_file(
            "name;code\nIdempotent Club;IDC001"
        ).decode("utf-8")
        second_payload = self._create_csv_file(
            "name;code\nDifferent Club;IDC002"
        ).decode("utf-8")

        self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=first_payload,
            source_reference="batch-200",
            idempotency_key="delivery-002",
        )

        with self.assertRaises(ValidationError):
            self.env["federation.integration.delivery"].stage_partner_delivery(
                partner=partner,
                contract=contract,
                filename="clubs.csv",
                payload_base64=second_payload,
                source_reference="batch-201",
                idempotency_key="delivery-002",
            )

    def test_inbound_delivery_reuses_idempotency_key_after_processing(self):
        """The same idempotency key should resolve to the original delivery even after processing."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        payload = self._create_csv_file("name;code\nProcessed Club;IDC003").decode(
            "utf-8"
        )

        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=payload,
            source_reference="batch-202",
            idempotency_key="delivery-003",
        )
        delivery.write(
            {
                "state": "processed",
                "processed_on": fields.Datetime.now(),
            }
        )

        replayed = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="clubs.csv",
            payload_base64=payload,
            source_reference="batch-202",
            idempotency_key="delivery-003",
        )

        self.assertEqual(delivery, replayed)

    def test_inbound_delivery_links_to_governed_import_flow(self):
        """Test that inbound delivery links to governed import flow."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        payload = self._create_csv_file("name;code\nDelivery Club;DC001").decode(
            "utf-8"
        )
        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="delivery-clubs.csv",
            payload_base64=payload,
        )

        action = delivery.action_open_import_wizard()
        wizard = self.env[action["res_model"]].browse(action["res_id"])

        self.assertEqual(wizard.integration_delivery_id, delivery)
        self.assertEqual(wizard.template_id, contract.import_template_id)

        wizard.action_parse_and_import()
        delivery.invalidate_recordset()
        self.assertEqual(delivery.state, "previewed")

        wizard.action_request_approval()
        delivery.invalidate_recordset()
        self.assertEqual(delivery.state, "awaiting_approval")
        self.assertEqual(delivery.governance_job_id, wizard.governance_job_id)

        wizard.action_approve_import()
        delivery.invalidate_recordset()
        self.assertEqual(delivery.state, "approved")

        wizard.dry_run = False
        wizard.action_parse_and_import()
        delivery.invalidate_recordset()

        self.assertEqual(delivery.state, "processed")
        self.assertEqual(delivery.governance_job_id.state, "completed")
        self.assertEqual(delivery.success_count, 1)
        self.assertTrue(
            self.env["federation.club"].search([("code", "=", "DC001")], limit=1)
        )

    def test_inbound_delivery_rejects_disallowed_payload_extension(self):
        """Inbound staging should reject payloads outside the shared extension allowlist."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)

        with self.assertRaises(ValidationError) as error:
            self.env["federation.integration.delivery"].stage_partner_delivery(
                partner=partner,
                contract=contract,
                filename="clubs.json",
                payload_base64=self._create_csv_file(
                    "name;code\nStaged Club;SC001"
                ).decode("utf-8"),
            )

        self.assertIn("extensions", str(error.exception))

    def test_failed_delivery_records_typed_operator_feedback(self):
        """Failed deliveries should store typed categories instead of raw exception text."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="delivery-clubs.csv",
            payload_base64=self._create_csv_file(
                "name;code\nDelivery Club;DC001"
            ).decode("utf-8"),
        )

        delivery.action_mark_failed("Preview checksum failed")

        self.assertEqual(delivery.failure_category, "data_validation")
        self.assertEqual(delivery.operator_message, "Preview checksum failed")
        self.assertEqual(delivery.result_message, "Preview checksum failed")

    def test_delivery_retention_purges_old_processed_records_and_payloads(self):
        """Retention should delete old terminal deliveries and their payload attachments."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="retained-clubs.csv",
            payload_base64=self._create_csv_file(
                "name;code\nRetained Club;RC001"
            ).decode("utf-8"),
        )
        attachment = delivery.attachment_id

        old_processed_on = fields.Datetime.to_string(
            fields.Datetime.to_datetime(fields.Datetime.now()) - timedelta(days=200)
        )
        delivery.write(
            {
                "state": "processed",
                "processed_on": old_processed_on,
            }
        )

        deleted = self.env[
            "federation.integration.delivery"
        ]._purge_retained_deliveries()

        self.assertEqual(deleted, 1)
        self.assertFalse(delivery.exists())
        self.assertFalse(attachment.exists())

    def test_inbound_delivery_rejects_oversized_payload(self):
        """Inbound staging should enforce the shared maximum payload size."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        max_bytes = self.env["federation.attachment.policy"].get_policy(
            "integration_inbound_csv"
        )["max_bytes"]
        oversized_payload = base64.b64encode(b"x" * (max_bytes + 1)).decode("utf-8")

        with self.assertRaises(ValidationError) as error:
            self.env["federation.integration.delivery"].stage_partner_delivery(
                partner=partner,
                contract=contract,
                filename="clubs.csv",
                payload_base64=oversized_payload,
            )

        self.assertIn("MiB or smaller", str(error.exception))

    def test_inbound_delivery_rejects_payloads_that_fail_malware_scan(self):
        """Inbound staging should surface the shared malware-scan rejection."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner, _subscription = self._create_integration_partner(contract)
        scanner = self.env["federation.attachment.scan.service"]

        with patch.object(
            type(scanner),
            "scan_upload",
            side_effect=ValidationError(
                "Uploaded files failed the federation malware scan."
            ),
        ):
            with self.assertRaises(ValidationError) as error:
                self.env["federation.integration.delivery"].stage_partner_delivery(
                    partner=partner,
                    contract=contract,
                    filename="clubs.csv",
                    payload_base64=self._create_csv_file(
                        "name;code\nBlocked Club;BC001"
                    ).decode("utf-8"),
                )

        self.assertIn("malware scan", str(error.exception))

    def test_import_teams_resolves_club_by_code(self):
        """Teams import should resolve parent clubs via club codes and create the record."""
        csv_content = (
            "club_code,team_name,code,category,gender,email,phone\n"
            "TC001,Reserve Team,TEAM002,youth,mixed,reserve@example.com,555"
        )
        wizard = self._approve_wizard_import(
            self.env["federation.import.teams.wizard"].create(
                {
                    "upload_file": self._create_csv_file(csv_content),
                    "dry_run": False,
                }
            )
        )

        wizard.action_parse_and_import()

        self.assertEqual(wizard.line_count, 1)
        self.assertEqual(wizard.success_count, 1)
        self.assertEqual(wizard.error_count, 0)

        team = self.env["federation.team"].search([("code", "=", "TEAM002")], limit=1)
        self.assertTrue(team)
        self.assertEqual(team.club_id, self.club)
        self.assertEqual(team.category, "youth")
        self.assertEqual(team.gender, "mixed")

    def test_import_players_splits_legacy_name_and_sets_club(self):
        """Players import should translate legacy full-name CSVs into first and last names."""
        csv_content = "name,birth_date,club_code,gender,state\nAlice Example,2005-04-06,TC001,female,active"
        wizard = self._approve_wizard_import(
            self.env["federation.import.players.wizard"].create(
                {
                    "upload_file": self._create_csv_file(csv_content),
                    "dry_run": False,
                }
            )
        )

        wizard.action_parse_and_import()

        self.assertEqual(wizard.line_count, 1)
        self.assertEqual(wizard.success_count, 1)
        self.assertEqual(wizard.error_count, 0)

        player = self.env["federation.player"].search(
            [
                ("first_name", "=", "Alice"),
                ("last_name", "=", "Example"),
            ],
            limit=1,
        )
        self.assertTrue(player)
        self.assertEqual(player.club_id, self.club)
        self.assertEqual(player.gender, "female")

    def test_import_seasons_reports_format_errors_by_category(self):
        """Season import should create valid rows and classify invalid date rows."""
        csv_content = (
            "name,code,date_start,date_end,state\n"
            "Season 2026,S2026,2026-01-01,2026-12-31,open\n"
            "Season 2027,S2027,2026/01/01,2026-12-31,open"
        )
        wizard = self.env["federation.import.seasons.wizard"].create(
            {
                "upload_file": self._create_csv_file(csv_content),
                "dry_run": False,
            }
        )

        self._approve_wizard_import(wizard)

        wizard.action_parse_and_import()

        self.assertEqual(wizard.line_count, 2)
        self.assertEqual(wizard.success_count, 1)
        self.assertEqual(wizard.error_count, 1)
        self.assertIn("format_error", wizard.result_message)

    def test_completed_import_job_records_typed_feedback_for_row_errors(self):
        """Approved imports with row errors should persist a typed operator summary."""
        csv_content = (
            "name,code,date_start,date_end,state\n"
            "Season 2028,S2028,2028-01-01,2028-12-31,open\n"
            "Season 2029,S2029,2028/01/01,2028-12-31,open"
        )
        wizard = self.env["federation.import.seasons.wizard"].create(
            {
                "upload_file": self._create_csv_file(csv_content),
                "dry_run": False,
            }
        )

        self._approve_wizard_import(wizard)
        wizard.action_parse_and_import()

        self.assertEqual(wizard.governance_job_id.state, "completed_with_errors")
        self.assertEqual(wizard.governance_job_id.failure_category, "data_validation")
        self.assertIn(
            "row-level validation errors", wizard.governance_job_id.operator_message
        )
        self.assertTrue(
            self.env["federation.season"].search([("code", "=", "S2028")], limit=1)
        )

    def test_import_seasons_supports_planning_targets(self):
        """Test that import seasons supports planning targets."""
        csv_content = (
            "name,code,date_start,date_end,state,target_club_count,target_team_count,target_tournament_count,target_participant_count\n"
            "Planning Season,SPLAN,2026-01-01,2026-12-31,draft,8,18,4,32"
        )
        wizard = self.env["federation.import.seasons.wizard"].create(
            {
                "upload_file": self._create_csv_file(csv_content),
                "dry_run": False,
            }
        )

        self._approve_wizard_import(wizard)
        wizard.action_parse_and_import()

        season = self.env["federation.season"].search([("code", "=", "SPLAN")], limit=1)
        self.assertTrue(season)
        self.assertEqual(season.target_club_count, 8)
        self.assertEqual(season.target_team_count, 18)
        self.assertEqual(season.target_tournament_count, 4)
        self.assertEqual(season.target_participant_count, 32)

    def test_import_tournament_participants_duplicate_skip(self):
        """Tournament participant import should block duplicate rows using the shared backend reason."""
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
            }
        )

        csv_content = (
            f"tournament_code,team_code\n{self.tournament.code},{self.team.code}"
        )
        wizard = self._approve_wizard_import(
            self.env["federation.import.tournament.participants.wizard"].create(
                {
                    "upload_file": self._create_csv_file(csv_content),
                    "dry_run": False,
                }
            )
        )

        wizard.action_parse_and_import()

        self.assertEqual(wizard.line_count, 1)
        self.assertEqual(wizard.success_count, 0)
        self.assertEqual(wizard.error_count, 1)
        self.assertIn(
            "A participant record already exists for this team.", wizard.result_message
        )
        self.assertIn("duplicate_entry", wizard.result_message)

    def test_import_tournament_participants_accepts_codes_and_seed(self):
        """Tournament participant import should resolve references by code and persist seed."""
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Spring Invitational",
                "code": "SPRING2026",
                "date_start": "2026-03-01",
                "date_end": "2026-03-02",
            }
        )
        team = self.env["federation.team"].create(
            {
                "name": "Seeded Team",
                "code": "TEAM003",
                "club_id": self.club.id,
            }
        )

        csv_content = f"tournament_code,team_code,seed\n{tournament.code},{team.code},4"
        wizard = self._approve_wizard_import(
            self.env["federation.import.tournament.participants.wizard"].create(
                {
                    "upload_file": self._create_csv_file(csv_content),
                    "dry_run": False,
                }
            )
        )

        wizard.action_parse_and_import()

        self.assertEqual(wizard.line_count, 1)
        self.assertEqual(wizard.success_count, 1)
        self.assertEqual(wizard.error_count, 0)

        participant = self.env["federation.tournament.participant"].search(
            [
                ("tournament_id", "=", tournament.id),
                ("team_id", "=", team.id),
            ],
            limit=1,
        )
        self.assertTrue(participant)
        self.assertEqual(participant.seed, 4)

    def test_import_wizard_live_success_returns_display_notification(self):
        """A clean live import (no errors) should return a display_notification action."""
        csv_content = "name;code\nNotification Club;NCLUB001"
        wizard = self._approve_wizard_import(
            self.env["federation.import.clubs.wizard"].create(
                {
                    "upload_file": self._create_csv_file(csv_content),
                    "dry_run": False,
                }
            )
        )

        result = wizard.action_parse_and_import()

        self.assertEqual(wizard.success_count, 1)
        self.assertEqual(wizard.error_count, 0)
        self.assertEqual(result.get("type"), "ir.actions.client")
        self.assertEqual(result.get("tag"), "display_notification")
        params = result.get("params", {})
        self.assertEqual(params.get("type"), "success")
        self.assertIn("1", params.get("message", ""))
        self.assertIsNotNone(params.get("next"))

    def test_import_wizard_dry_run_returns_reopen_wizard(self):
        """A dry-run import should reopen the wizard form (not show a notification)."""
        csv_content = "name;code\nDryRun Club;DRCLUB"
        wizard = self.env["federation.import.clubs.wizard"].create(
            {
                "upload_file": self._create_csv_file(csv_content),
                "dry_run": True,
            }
        )

        result = wizard.action_parse_and_import()

        self.assertEqual(result.get("type"), "ir.actions.act_window")
        self.assertEqual(result.get("res_model"), "federation.import.clubs.wizard")

    def test_import_wizard_live_with_errors_returns_reopen_wizard(self):
        """A live import with row errors should reopen the wizard (not show success notification)."""
        # Create a club that will cause a duplicate error
        self.env["federation.club"].create({"name": "Existing Club", "code": "EXCLUB"})

        csv_content = "name;code\nExisting Club;EXCLUB"
        wizard = self._approve_wizard_import(
            self.env["federation.import.clubs.wizard"].create(
                {
                    "upload_file": self._create_csv_file(csv_content),
                    "dry_run": False,
                }
            )
        )

        result = wizard.action_parse_and_import()

        self.assertEqual(wizard.error_count, 1)
        self.assertEqual(wizard.success_count, 0)
        self.assertEqual(result.get("type"), "ir.actions.act_window")
        self.assertEqual(result.get("res_model"), "federation.import.clubs.wizard")
