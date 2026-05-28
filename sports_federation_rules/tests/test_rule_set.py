from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger


class TestFederationRuleSet(TransactionCase):
    """Tests for federation.rule.set and related models."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Standard League Rules",
                "code": "SLR",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
                "squad_min_size": 11,
                "squad_max_size": 25,
                "referee_required_count": 3,
                "seeding_mode": "ranking",
            }
        )

    def test_create_rule_set(self):
        """Test creating a basic rule set."""
        self.assertEqual(self.rule_set.name, "Standard League Rules")
        self.assertEqual(self.rule_set.code, "SLR")
        self.assertEqual(self.rule_set.points_win, 3)
        self.assertEqual(self.rule_set.points_draw, 1)
        self.assertEqual(self.rule_set.points_loss, 0)

    def test_rule_set_code_unique(self):
        """Test that rule set code must be unique."""
        with self.assertRaises(Exception), mute_logger(
            "odoo.sql_db"
        ), self.cr.savepoint():
            self.env["federation.rule.set"].create(
                {
                    "name": "Duplicate Rules",
                    "code": "SLR",
                }
            )

    def test_squad_size_constraint(self):
        """Test that min squad size cannot exceed max."""
        with self.assertRaises(ValidationError):
            self.env["federation.rule.set"].create(
                {
                    "name": "Bad Squad Rules",
                    "code": "BSR",
                    "squad_min_size": 30,
                    "squad_max_size": 20,
                }
            )

    def test_points_rules(self):
        """Test creating points rules linked to a rule set."""
        self.env["federation.points.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "result_type": "win",
                "points": 3,
            }
        )
        self.env["federation.points.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "result_type": "draw",
                "points": 1,
            }
        )
        self.env["federation.points.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "result_type": "loss",
                "points": 0,
            }
        )
        self.assertEqual(len(self.rule_set.points_rule_ids), 3)

    def test_points_rule_uniqueness(self):
        """Test that each result type can only appear once per rule set."""
        self.env["federation.points.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "result_type": "win",
                "points": 3,
            }
        )
        with self.assertRaises(Exception), mute_logger(
            "odoo.sql_db"
        ), self.cr.savepoint():
            self.env["federation.points.rule"].create(
                {
                    "rule_set_id": self.rule_set.id,
                    "result_type": "win",
                    "points": 5,
                }
            )

    def test_tie_break_rules(self):
        """Test creating ordered tie-break rules."""
        tb1 = self.env["federation.tie_break.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "sequence": 10,
                "tie_break_type": "head_to_head",
            }
        )
        tb2 = self.env["federation.tie_break.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "sequence": 20,
                "tie_break_type": "goal_difference",
            }
        )
        tb3 = self.env["federation.tie_break.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "sequence": 30,
                "tie_break_type": "goals_scored",
            }
        )
        self.assertEqual(len(self.rule_set.tie_break_rule_ids), 3)
        # Verify ordering
        self.assertEqual(self.rule_set.tie_break_rule_ids[0], tb1)
        self.assertEqual(self.rule_set.tie_break_rule_ids[1], tb2)
        self.assertEqual(self.rule_set.tie_break_rule_ids[2], tb3)

    def test_tie_break_type_uniqueness(self):
        """Test that each tie-break type can only appear once per rule set."""
        self.env["federation.tie_break.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "sequence": 10,
                "tie_break_type": "head_to_head",
            }
        )
        with self.assertRaises(Exception), mute_logger(
            "odoo.sql_db"
        ), self.cr.savepoint():
            self.env["federation.tie_break.rule"].create(
                {
                    "rule_set_id": self.rule_set.id,
                    "sequence": 20,
                    "tie_break_type": "head_to_head",
                }
            )

    def test_eligibility_rules(self):
        """Test creating eligibility rules."""
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "name": "Minimum Age 16",
                "eligibility_type": "age_min",
                "age_limit": 16,
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "name": "Valid License Required",
                "eligibility_type": "license_valid",
            }
        )
        self.assertEqual(len(self.rule_set.eligibility_rule_ids), 2)

    def test_eligibility_placeholder(self):
        """Test placeholder eligibility rules."""
        placeholder = self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "name": "Future Gender Check",
                "eligibility_type": "gender",
                "is_placeholder": True,
            }
        )
        self.assertTrue(placeholder.is_placeholder)

    def test_qualification_rules(self):
        """Test creating qualification rules."""
        top_n = self.env["federation.qualification.rule"].create(
            {
                "rule_set_id": self.rule_set.id,
                "name": "Top 4 Qualify",
                "qualification_type": "top_n",
                "value_integer": 4,
            }
        )
        self.assertEqual(len(self.rule_set.qualification_rule_ids), 1)
        self.assertEqual(top_n.rule_set_id, self.rule_set)
