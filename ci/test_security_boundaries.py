import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


privileged = load("check_privileged_mutation_boundaries")
destructive = load("check_destructive_token_contract")
audit_acl = load("check_audit_acl_integrity")


def write_controller(root, body):
    path = root / "sports_federation_sample" / "controllers" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text(body)
    return path


def test_direct_elevated_controller_mutation_is_rejected(tmp_path):
    write_controller(
        tmp_path,
        "def route(request):\n"
        "    request.env['sample.model'].sudo().write({'name': 'unsafe'})\n",
    )
    violations = privileged.find_violations(tmp_path)
    assert len(violations) == 1
    assert "elevated record with write()" in violations[0]


def test_privilege_service_call_is_allowed(tmp_path):
    write_controller(
        tmp_path,
        "def route(request, record):\n"
        "    request.env['federation.portal.privilege'].portal_call(\n"
        "        record, 'action_submit', scope_domain=[('id', '=', record.id)]\n"
        "    )\n",
    )
    assert privileged.find_violations(tmp_path) == []


def test_repository_destructive_token_consumers_follow_contract():
    assert destructive.find_violations(ROOT) == []


def test_audit_acl_checker_rejects_unlink_permissions(tmp_path):
    path = tmp_path / "sports_federation_sample" / "security" / "ir.model.access.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        "access_audit,audit,model_federation_audit_event,base.group_system,1,1,1,1\n"
    )
    violations = audit_acl.find_violations(tmp_path)
    assert len(violations) == 1
    assert "immutable audit evidence" in violations[0]


def test_repository_audit_acls_deny_unlink():
    assert audit_acl.find_violations(ROOT) == []


def test_privileged_command_contracts_are_complete():
    commands = load("check_privileged_command_contracts")
    assert commands.find_violations(ROOT) == []


def test_result_portal_uses_owned_command_service():
    path = ROOT / "sports_federation_portal/controllers/result_portal.py"
    source = path.read_text()
    assert 'request.env["federation.result.commands"]' in source
    assert "match.action_approve_result()" not in source
    assert "match.action_contest_result()" not in source


def test_workflow_transition_foundation_is_wired():
    transitions = load("check_workflow_transition_foundation")
    assert transitions.find_violations(ROOT) == []


def test_matchday_transition_contract_is_complete():
    contract = load("check_matchday_transition_contract")
    assert contract.find_violations(ROOT) == []


def test_result_transition_contract_is_complete():
    contract = load("check_result_transition_contract")
    assert contract.find_violations(ROOT) == []


def test_browser_test_runtime_is_locked():
    runtime = load("check_browser_test_runtime")
    assert runtime.find_violations(ROOT) == []


def test_release_baseline_evidence_is_isolated():
    contract = load("check_release_baseline_evidence")
    assert contract.find_violations(ROOT) == []


def test_release_failure_classification_is_actionable():
    classifier = load("classify_release_failure")
    assert (
        classifier.classify("Release workspace contains tracked changes", "preflight")
        == "unsupported_configuration"
    )
    assert (
        classifier.classify("ValidationError: workflow rejected", "full")
        == "product_defect"
    )
    assert (
        classifier.classify("websocket-client module is not installed", "acceptance")
        == "unsupported_configuration"
    )
