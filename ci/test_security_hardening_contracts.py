"""Fast source contracts for the Priority A security boundary."""

import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_global_search_never_uses_sudo():
    source = read("sports_federation_portal/models/qol_search.py")
    assert "model.sudo().search" not in source
    assert "_scope_domain" in source
    assert "model.search(domain" in source


def test_portal_capabilities_are_explicit():
    source = read("sports_federation_portal/models/portal_privilege.py")
    assert "PORTAL_CREATE_FIELDS" in source
    assert "PORTAL_ACTION_ALLOWLIST" in source
    assert "method_name not in allowed_actions" in source
    assert "set(values) - effective" in source


def _portal_create_fields():
    tree = ast.parse(read("sports_federation_portal/models/portal_privilege.py"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PORTAL_CREATE_FIELDS"
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("PORTAL_CREATE_FIELDS not found")


def test_lineup_line_create_allowlist_matches_model_and_payload():
    """A key outside the allowlist turns a line-up save into Access Denied."""
    allowed = _portal_create_fields()["federation.match.sheet.line"]
    model = read("sports_federation_rosters/models/match_sheet_line.py")
    model_fields = set(re.findall(r"^    (\w+) = fields\.", model, re.M))
    assert allowed <= model_fields, sorted(allowed - model_fields)

    source = read("sports_federation_portal/models/federation_match_sheet.py")
    start = source.index('self.env["federation.match.sheet.line"],')
    payload = source[start : source.index("},", start)]
    sent = set(re.findall(r'"(\w+)":', payload))
    assert sent and sent <= allowed, sorted(sent - allowed)


def test_forwarded_headers_require_trusted_proxy():
    for path in (
        "sports_federation_public_site/controllers/_public_request.py",
        "sports_federation_import_tools/controllers/integration_api_auth_mixin.py",
    ):
        source = read(path)
        assert "federation.trusted_proxy_networks" in source
        assert "if trusted:" in source
        assert "ip_network" in source


def test_public_profile_excludes_draft_licences():
    source = read("sports_federation_public_site/controllers/public_clubs_players.py")
    assert 'lic.state == "active"' in source
    assert 'lic.state in ("active", "draft")' not in source


def test_eligibility_has_fail_closed_outcomes():
    source = read("sports_federation_rules/services/eligibility.py")
    assert 'REVIEW_REQUIRED = "review_required"' in source
    assert "no rule set is configured" in source
    assert "requires a configured evaluator" in source
