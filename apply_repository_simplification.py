from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTING = ROOT / "sports_federation_reporting"


def append_once(path, lines):
    content = path.read_text()
    missing = [line for line in lines if line not in content]
    if missing:
        path.write_text(content.rstrip() + "\n" + "\n".join(missing) + "\n")


append_once(
    REPORTING / "models" / "__init__.py",
    ["from . import report_catalog"],
)
append_once(
    REPORTING / "tests" / "__init__.py",
    ["from . import test_report_catalog"],
)
manifest_path = REPORTING / "__manifest__.py"
manifest = manifest_path.read_text()
if '"views/report_catalog_views.xml"' not in manifest:
    marker = '"views/menu_views.xml",'
    if marker not in manifest:
        raise SystemExit("Could not find reporting manifest insertion point")
    manifest = manifest.replace(
        marker,
        '"views/report_catalog_views.xml",\n        ' + marker,
        1,
    )
manifest = manifest.replace('"version": "19.0.1.4.1"', '"version": "19.0.2.0.0"')
manifest_path.write_text(manifest)

access_path = REPORTING / "security" / "ir.model.access.csv"
access_line = (
    "access_federation_report_catalog_manager,Report catalog manager,"
    "model_federation_report_catalog,sports_federation_base.group_federation_manager,"
    "1,1,1,1"
)
access = access_path.read_text()
if access_line not in access:
    access_path.write_text(access.rstrip() + "\n" + access_line + "\n")
