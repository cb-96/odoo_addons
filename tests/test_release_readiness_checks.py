import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


views = load("view_check", "ci/check_always_invisible_fields.py")
browser = load("browser_check", "ci/check_browser_release_log.py")


def test_invisible_field_requires_rationale(tmp_path):
    xml = tmp_path / "view.xml"
    xml.write_text('<form>\n<field name="active" invisible="1"/>\n</form>')
    assert views.violations(xml)
    xml.write_text(
        '<form>\n<!-- Technical field used by a modifier. -->\n<field name="active" invisible="1"/>\n</form>'
    )
    assert views.violations(xml) == []


def test_browser_log_rejects_missing_runtime(tmp_path):
    log = tmp_path / "focus.log"
    log.write_text("websocket-client module is not installed")
    assert "missing websocket client" in browser.inspect(log)


def test_browser_log_accepts_clean_run(tmp_path):
    log = tmp_path / "focus.log"
    log.write_text("0 failed, 0 error(s) of 93 tests")
    assert browser.inspect(log) == []
