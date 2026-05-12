from io import BytesIO
from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import mute_logger
from datetime import date, timedelta


class TestCompliance(TransactionCase):
    """Test cases for the sports_federation_compliance module."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()

        cls.portal_club_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.portal_official_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_official"
        )
        cls.portal_role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )

        # Create test club
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TC001",
            }
        )

        # Create test player
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "John",
                "last_name": "Doe",
                "birth_date": "1990-01-01",
            }
        )

        # Create test referee
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Jane Smith",
                "email": "jane@example.com",
            }
        )

        # Create test venue
        cls.venue = cls.env["federation.venue"].create(
            {
                "name": "Test Stadium",
                "city": "Test City",
            }
        )

        cls.club_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Compliance Club User",
                    "login": "compliance.club@example.com",
                    "email": "compliance.club@example.com",
                    "group_ids": [(6, 0, [cls.portal_club_group.id])],
                }
            )
        )
        cls.referee_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Compliance Referee User",
                    "login": "compliance.referee@example.com",
                    "email": "compliance.referee@example.com",
                    "group_ids": [(6, 0, [cls.portal_official_group.id])],
                }
            )
        )
        cls.club_representative = cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.club_user.partner_id.id,
                "user_id": cls.club_user.id,
                "role_type_id": cls.portal_role_type.id,
            }
        )
        cls.referee.user_id = cls.referee_user

        # Create test requirement
        cls.requirement = cls.env["federation.document.requirement"].create(
            {
                "name": "Club Registration",
                "code": "CLUB_REG",
                "target_model": "federation.club",
                "requires_expiry_date": True,
                "validity_days": 365,
            }
        )

        # Create a requirement without expiry date constraint
        cls.requirement_no_expiry = cls.env["federation.document.requirement"].create(
            {
                "name": "Club Info",
                "code": "CLUB_INFO",
                "target_model": "federation.club",
                "requires_expiry_date": False,
            }
        )
        cls.referee_requirement = cls.env["federation.document.requirement"].create(
            {
                "name": "Referee License",
                "code": "REF_LIC",
                "target_model": "federation.referee",
                "requires_expiry_date": True,
            }
        )

    def test_create_requirement(self):
        """Test creating a document requirement."""
        requirement = self.env["federation.document.requirement"].create(
            {
                "name": "Player License",
                "code": "PLAYER_LIC",
                "target_model": "federation.player",
            }
        )
        self.assertTrue(requirement.id)
        self.assertEqual(requirement.name, "Player License")
        self.assertEqual(requirement.target_model, "federation.player")

    def test_requirement_unique_code_target(self):
        """Test unique constraint on (code, target_model)."""
        with self.assertRaises(Exception), mute_logger(
            "odoo.sql_db"
        ), self.cr.savepoint():
            self.env["federation.document.requirement"].create(
                {
                    "name": "Duplicate Requirement",
                    "code": "CLUB_REG",  # Same code as setUpClass
                    "target_model": "federation.club",  # Same target_model
                }
            )

    def test_shared_target_field_resolver_is_consistent(self):
        """Test that compliance models share the same target field resolver."""
        expected_map = {
            "federation.club": "club_id",
            "federation.player": "player_id",
            "federation.referee": "referee_id",
            "federation.venue": "venue_id",
            "federation.club.representative": "club_representative_id",
        }

        requirement_model = self.env["federation.document.requirement"]
        check_model = self.env["federation.compliance.check"]
        submission_model = self.env["federation.document.submission"]

        self.assertEqual(requirement_model._portal_target_field_map(), expected_map)
        for target_model, field_name in expected_map.items():
            self.assertEqual(
                requirement_model._portal_get_target_field_name(target_model),
                field_name,
            )
            self.assertEqual(
                check_model._compliance_get_target_field_name(target_model), field_name
            )
            self.assertEqual(
                submission_model._compliance_get_target_field_name(target_model),
                field_name,
            )

    def test_shared_target_record_resolution_sets_display(self):
        """Test shared target resolution on submissions and checks."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Resolver Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        check = self.env["federation.compliance.check"].create(
            {
                "name": "Resolver Check",
                "target_model": "federation.club",
                "club_id": self.club.id,
                "status": "missing",
                "requirement_id": self.requirement.id,
            }
        )

        self.assertEqual(submission._get_target_record(), self.club)
        self.assertEqual(submission.target_display, self.club.display_name)
        self.assertEqual(
            check._get_target_field_value(check, "federation.club"), self.club
        )
        self.assertEqual(check.target_display, self.club.display_name)

    def test_submission_requires_single_target(self):
        """Test that exactly one target entity must be set."""
        # No target set
        with self.assertRaises(ValidationError):
            submission = self.env["federation.document.submission"].create(
                {
                    "name": "Test Submission",
                    "requirement_id": self.requirement.id,
                }
            )
            submission._check_single_target()

        # Multiple targets set
        with self.assertRaises(ValidationError):
            submission = self.env["federation.document.submission"].create(
                {
                    "name": "Test Submission",
                    "requirement_id": self.requirement.id,
                    "club_id": self.club.id,
                    "player_id": self.player.id,
                }
            )
            submission._check_single_target()

    def test_submission_target_matches_requirement_model(self):
        """Test that target matches requirement.target_model."""
        # Requirement is for club, but setting player should fail
        with self.assertRaises(ValidationError):
            submission = self.env["federation.document.submission"].create(
                {
                    "name": "Test Submission",
                    "requirement_id": self.requirement.id,
                    "player_id": self.player.id,  # Wrong target for club requirement
                }
            )
            submission._check_target_matches_requirement()

        # Correct target should work
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        self.assertEqual(submission.target_model, "federation.club")
        self.assertEqual(submission.club_id, self.club)

    def test_submission_date_validation(self):
        """Test that expiry_date >= issue_date if both set."""
        with self.assertRaises(ValidationError):
            self.env["federation.document.submission"].create(
                {
                    "name": "Test Submission",
                    "requirement_id": self.requirement.id,
                    "club_id": self.club.id,
                    "issue_date": date.today(),
                    "expiry_date": date.today()
                    - timedelta(days=1),  # Before issue date
                }
            )

    def test_submission_workflow(self):
        """Test submission workflow: draft -> submitted -> approved."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        self.assertEqual(submission.status, "draft")

        submission.action_submit()
        self.assertEqual(submission.status, "submitted")

        submission.action_approve()
        self.assertEqual(submission.status, "approved")
        self.assertTrue(submission.reviewer_id)
        self.assertTrue(submission.reviewed_on)

    def test_submission_reject(self):
        """Test submission rejection."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        submission.action_submit()
        submission.action_reject()
        self.assertEqual(submission.status, "rejected")

    def test_submission_request_replacement(self):
        """Test requesting replacement for approved document."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        submission.action_submit()
        submission.action_approve()
        submission.action_request_replacement()
        self.assertEqual(submission.status, "replacement_requested")

    def test_check_detects_missing_document(self):
        """Test that compliance check detects missing document."""
        checks = self.env["federation.compliance.check"].recompute_checks_for_target(
            self.club, "federation.club"
        )
        self.assertTrue(len(checks) > 0)
        missing_checks = [c for c in checks if c.status == "missing"]
        self.assertTrue(missing_checks)
        self.assertEqual(missing_checks[0].note, "No submission found")

    def test_check_detects_valid_approved_document(self):
        """Test that compliance check detects valid approved document."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "issue_date": date.today(),
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        submission.action_submit()
        submission.action_approve()

        checks = self.env["federation.compliance.check"].recompute_checks_for_target(
            self.club, "federation.club"
        )
        compliant_checks = [c for c in checks if c.status == "compliant"]
        self.assertTrue(compliant_checks)
        self.assertEqual(compliant_checks[0].note, "Document is valid")
        self.assertEqual(compliant_checks[0].submission_id, submission)

    def test_check_detects_expired_document(self):
        """Test that compliance check detects expired document."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "issue_date": date.today() - timedelta(days=400),
                "expiry_date": date.today() - timedelta(days=1),  # Expired
            }
        )
        submission.action_submit()
        submission.action_approve()

        checks = self.env["federation.compliance.check"].recompute_checks_for_target(
            self.club, "federation.club"
        )
        expired_checks = [c for c in checks if c.status == "expired"]
        self.assertTrue(expired_checks)
        self.assertEqual(expired_checks[0].note, "Document has expired")

    def test_compliance_check_history_archives_status_changes(self):
        """Test that compliance check history archives status changes."""
        checks = self.env["federation.compliance.check"].recompute_checks_for_target(
            self.club, "federation.club"
        )
        check = next(
            candidate
            for candidate in checks
            if candidate.requirement_id == self.requirement
        )
        initial_archive_count = self.env[
            "federation.compliance.check.archive"
        ].search_count(
            [
                ("compliance_check_id", "=", check.id),
            ]
        )

        submission = self.env["federation.document.submission"].create(
            {
                "name": "Archived Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "issue_date": date.today(),
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        submission.action_submit()
        submission.action_approve()

        refreshed_checks = self.env[
            "federation.compliance.check"
        ].recompute_checks_for_target(self.club, "federation.club")
        check = next(
            candidate
            for candidate in refreshed_checks
            if candidate.requirement_id == self.requirement
        )

        archives = self.env["federation.compliance.check.archive"].search(
            [
                ("compliance_check_id", "=", check.id),
            ],
            order="archived_on asc, id asc",
        )

        self.assertGreater(len(archives), initial_archive_count)
        self.assertEqual(archives[0].status, "missing")
        self.assertEqual(archives[-1].status, "compliant")

    def test_check_single_target(self):
        """Test that compliance check requires exactly one target."""
        with self.assertRaises(ValidationError):
            self.env["federation.compliance.check"].create(
                {
                    "name": "Test Check",
                    "target_model": "federation.club",
                    "status": "compliant",
                    "requirement_id": self.requirement.id,
                }
            )

    def test_is_expired_helper(self):
        """Test the is_expired computed field."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() - timedelta(days=1),
            }
        )
        self.assertTrue(submission.is_expired)

        submission2 = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission 2",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=30),
            }
        )
        self.assertFalse(submission2.is_expired)

        submission3 = self.env["federation.document.submission"].create(
            {
                "name": "Test Submission 3",
                "requirement_id": self.requirement_no_expiry.id,
                "club_id": self.club.id,
            }
        )
        self.assertFalse(submission3.is_expired)

    def test_portal_workspace_entries_follow_club_and_referee_scope(self):
        """Test that portal workspace entries follow club and referee scope."""
        Requirement = self.env["federation.document.requirement"]

        club_entries = Requirement._portal_get_workspace_entries(user=self.club_user)
        referee_entries = Requirement._portal_get_workspace_entries(
            user=self.referee_user
        )

        self.assertTrue(
            any(
                entry["requirement"] == self.requirement
                and entry["target"] == self.club
                for entry in club_entries
            )
        )
        self.assertTrue(
            any(
                entry["requirement"] == self.referee_requirement
                and entry["target"] == self.referee
                for entry in referee_entries
            )
        )
        self.assertFalse(
            any(
                entry["requirement"] == self.referee_requirement
                for entry in club_entries
            )
        )

    def test_portal_workspace_entry_lookup_resolves_club_detail_entry(self):
        """Test that portal workspace entry lookup resolves club detail entry."""
        entry = (
            self.env["federation.document.requirement"]
            .with_user(self.club_user)
            ._portal_get_workspace_entry_for_user(
                self.requirement.id,
                "federation.club",
                self.club.id,
                user=self.club_user,
            )
        )

        self.assertTrue(entry)
        self.assertEqual(
            entry["detail_url"],
            f"/my/compliance/{self.requirement.id}/federation.club/{self.club.id}",
        )

    def test_portal_prepare_submission_uses_requesting_user(self):
        """Test that portal prepare submission uses requesting user."""
        submission = self.env[
            "federation.document.submission"
        ]._portal_prepare_submission(
            self.requirement,
            self.club,
            values={
                "issue_date": date.today(),
                "expiry_date": date.today() + timedelta(days=365),
                "notes": "Uploaded from portal helper.",
            },
            user=self.club_user,
        )

        self.assertEqual(submission.status, "draft")
        self.assertEqual(submission.club_id, self.club)
        self.assertEqual(submission.create_uid, self.club_user)
        self.assertEqual(submission.notes, "Uploaded from portal helper.")

        submission.with_user(self.club_user).sudo().action_submit()
        self.assertEqual(submission.status, "submitted")

    def test_portal_prepare_submission_blocks_unowned_targets(self):
        """Test that portal prepare submission blocks unowned targets."""
        other_club = self.env["federation.club"].create(
            {
                "name": "Other Club",
                "code": "OC001",
            }
        )

        with self.assertRaises(AccessError):
            self.env["federation.document.submission"]._portal_prepare_submission(
                self.requirement,
                other_club,
                values={
                    "expiry_date": date.today() + timedelta(days=365),
                },
                user=self.club_user,
            )

    def test_portal_submit_submission_creates_attachments_and_submits(self):
        """Test that portal submit helper attaches files and submits the record."""
        upload = BytesIO(b"club-compliance-payload")
        upload.filename = "club-insurance.pdf"
        upload.mimetype = "application/pdf"

        submission = self.env[
            "federation.document.submission"
        ]._portal_submit_submission(
            self.requirement,
            self.club,
            values={
                "issue_date": date.today(),
                "expiry_date": date.today() + timedelta(days=365),
                "notes": "Submitted from the portal helper.",
            },
            uploaded_files=[upload],
            user=self.club_user,
        )

        self.assertEqual(submission.status, "submitted")
        self.assertEqual(submission.create_uid, self.club_user)
        self.assertEqual(len(submission.attachment_ids), 1)
        self.assertEqual(submission.attachment_ids[0].name, "club-insurance.pdf")

    def test_portal_submit_submission_requires_attachment(self):
        """Test that portal submit helper still rejects attachment-less submissions."""
        with self.assertRaises(ValidationError):
            self.env["federation.document.submission"]._portal_submit_submission(
                self.requirement,
                self.club,
                values={
                    "expiry_date": date.today() + timedelta(days=365),
                },
                uploaded_files=[],
                user=self.club_user,
            )

    def test_portal_submit_submission_rejects_disallowed_attachment_type(self):
        """Portal submit helper should reject files outside the shared allowlist."""
        upload = BytesIO(b"club-compliance-payload")
        upload.filename = "club-insurance.exe"
        upload.mimetype = "application/octet-stream"

        with self.assertRaises(ValidationError) as error:
            self.env["federation.document.submission"]._portal_submit_submission(
                self.requirement,
                self.club,
                values={
                    "expiry_date": date.today() + timedelta(days=365),
                },
                uploaded_files=[upload],
                user=self.club_user,
            )

        self.assertIn("extensions", str(error.exception))

    def test_portal_submit_submission_rejects_oversized_attachment(self):
        """Portal submit helper should enforce the shared maximum attachment size."""
        max_bytes = self.env["federation.attachment.policy"].get_policy(
            "portal_document"
        )["max_bytes"]
        upload = BytesIO(b"x" * (max_bytes + 1))
        upload.filename = "club-insurance.pdf"
        upload.mimetype = "application/pdf"

        with self.assertRaises(ValidationError) as error:
            self.env["federation.document.submission"]._portal_submit_submission(
                self.requirement,
                self.club,
                values={
                    "expiry_date": date.today() + timedelta(days=365),
                },
                uploaded_files=[upload],
                user=self.club_user,
            )

        self.assertIn("MiB or smaller", str(error.exception))

    def test_portal_submit_submission_rejects_attachment_that_fails_malware_scan(self):
        """Portal submit helper should surface shared malware-scan failures."""
        upload = BytesIO(b"portal-malware-test")
        upload.filename = "club-insurance.pdf"
        upload.mimetype = "application/pdf"
        scanner = self.env["federation.attachment.scan.service"]

        with patch.object(
            type(scanner),
            "scan_upload",
            side_effect=ValidationError(
                "Uploaded files failed the federation malware scan."
            ),
        ):
            with self.assertRaises(ValidationError) as error:
                self.env["federation.document.submission"]._portal_submit_submission(
                    self.requirement,
                    self.club,
                    values={
                        "expiry_date": date.today() + timedelta(days=365),
                    },
                    uploaded_files=[upload],
                    user=self.club_user,
                )

        self.assertIn("malware scan", str(error.exception))

    def test_portal_submit_submission_dedupes_duplicate_attachments(self):
        """Portal submit helper should keep one attachment per checksum."""
        first_upload = BytesIO(b"duplicate-compliance-payload")
        first_upload.filename = "club-insurance.pdf"
        first_upload.mimetype = "application/pdf"
        second_upload = BytesIO(b"duplicate-compliance-payload")
        second_upload.filename = "club-insurance-copy.pdf"
        second_upload.mimetype = "application/pdf"

        submission = self.env[
            "federation.document.submission"
        ]._portal_submit_submission(
            self.requirement,
            self.club,
            values={
                "expiry_date": date.today() + timedelta(days=365),
            },
            uploaded_files=[first_upload, second_upload],
            user=self.club_user,
        )

        self.assertEqual(len(submission.attachment_ids), 1)

    def test_target_entity_label_returns_correct_name(self):
        """target_entity_label returns the display name of the resolved target entity."""
        player_req = self.env["federation.document.requirement"].create(
            {
                "name": "Player Card",
                "code": "PLAY_CARD",
                "target_model": "federation.player",
            }
        )
        referee_req = self.env["federation.document.requirement"].create(
            {
                "name": "Referee Badge",
                "code": "REF_BADGE",
                "target_model": "federation.referee",
            }
        )

        club_sub = self.env["federation.document.submission"].create(
            {
                "name": "Club Label Test",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )
        player_sub = self.env["federation.document.submission"].create(
            {
                "name": "Player Label Test",
                "requirement_id": player_req.id,
                "player_id": self.player.id,
            }
        )
        referee_sub = self.env["federation.document.submission"].create(
            {
                "name": "Referee Label Test",
                "requirement_id": referee_req.id,
                "referee_id": self.referee.id,
                "expiry_date": date.today() + timedelta(days=365),
            }
        )

        self.assertEqual(club_sub.target_entity_label, self.club.display_name)
        self.assertEqual(player_sub.target_entity_label, self.player.display_name)
        self.assertEqual(referee_sub.target_entity_label, self.referee.display_name)
