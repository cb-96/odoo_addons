"""Dependency-free source/behavior checks; does not replace Odoo integration tests."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

class UsabilityChecks(unittest.TestCase):
    def test_python_and_xml(self):
        for module in ('sports_federation_setup_flow', 'sports_federation_rosters', 'sports_federation_portal'):
            for path in (ROOT / module).rglob('*'):
                if path.suffix == '.py': ast.parse(path.read_text())
                elif path.suffix == '.xml': ET.parse(path)

    def test_preview_behavior(self):
        tree = ast.parse((ROOT / 'sports_federation_setup_flow/wizards/format_setup_wizard.py').read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_compute_format_preview')
        method.decorator_list = []
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<preview>', 'exec'), namespace)
        for n, kind, matches, per_team, byes in [(4,'single_round_robin',6,3,0),(4,'double_round_robin',12,6,0),(5,'knockout',4,0,3),(0,'knockout',0,0,0),(1,'single_round_robin',0,0,0)]:
            wizard = SimpleNamespace(participant_set_id=SimpleNamespace(line_ids=list(range(n))), format_type=kind)
            namespace['_compute_format_preview']([wizard])
            self.assertEqual((wizard.preview_match_count,wizard.preview_matches_per_team,wizard.preview_byes),(matches,per_team,byes))

    def test_no_elevation_or_mutation_in_task_projection(self):
        tree=ast.parse((ROOT/'sports_federation_setup_flow/models/competition_planner.py').read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_usability_pending_tasks')
        calls=[n.func.attr for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertFalse(set(calls)&{'sudo','create','write','unlink'})
        self.assertIn('check_access',calls)

    def test_result_entry_uses_governed_submission(self):
        text=(ROOT/'sports_federation_setup_flow/wizards/quick_result_wizard.py').read_text()
        for required in ['match.check_access("write")','match._lock_result_transition()','match.action_submit_result()','score_entry_confirmed','zero_zero_confirmed']:
            self.assertIn(required,text)
        self.assertNotIn('sudo(',text)
        self.assertNotIn('workflow_policy_bypass',text)

    def test_recovery_excludes_sensitive_inputs(self):
        text=(ROOT/'sports_federation_portal/static/src/js/qol_draft_guard.js').read_text()
        self.assertIn('sessionStorage',text)
        self.assertIn('data',text)
        self.assertIn('draftUser',text)
        self.assertIn('24 * 60 * 60 * 1000',text)
        self.assertIn('["file", "password", "hidden"]',text)
        self.assertNotIn('localStorage',text)

if __name__=='__main__': unittest.main()
