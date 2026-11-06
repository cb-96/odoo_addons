"""The gate must propagate failures rather than print a reassuring success."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from unittest.mock import patch
import unittest

from ci import run_behavioral_contracts as gate


class TestBehavioralGate(unittest.TestCase):
    def test_structural_failure_returns_nonzero_without_loading_tests(self):
        with patch("ci.check_task_projection.violations", return_value=["broken boundary"]), \
                patch("ci.check_notification_side_effect_contract.violations", return_value=[]), \
                patch.object(unittest.defaultTestLoader, "loadTestsFromName") as load, \
                redirect_stderr(StringIO()):
            self.assertEqual(gate.main(), 1)
        load.assert_not_called()

    def test_behavioral_failure_returns_nonzero(self):
        class Broken(unittest.TestCase):
            def runTest(self):
                self.fail("intentional regression")
        with patch("ci.check_task_projection.violations", return_value=[]), \
                patch("ci.check_notification_side_effect_contract.violations", return_value=[]), \
                patch.object(unittest.defaultTestLoader, "loadTestsFromName",
                             side_effect=lambda name: unittest.TestSuite([Broken()])), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(gate.main(), 1)

    def test_success_identifies_isolated_scope(self):
        output = StringIO()
        with patch("ci.check_task_projection.violations", return_value=[]), \
                patch("ci.check_notification_side_effect_contract.violations", return_value=[]), \
                patch.object(unittest.defaultTestLoader, "loadTestsFromName",
                             side_effect=lambda name: unittest.TestSuite()), \
                redirect_stdout(output), redirect_stderr(StringIO()):
            self.assertEqual(gate.main(), 0)
        self.assertIn("ORM and browser suites were not run", output.getvalue())


if __name__ == "__main__":
    unittest.main()
