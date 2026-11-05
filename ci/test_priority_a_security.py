"""Fast source contracts for the Priority A security boundary."""
from pathlib import Path

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
