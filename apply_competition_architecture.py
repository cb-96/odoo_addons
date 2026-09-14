from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADDON = ROOT / "sports_federation_setup_flow"


def append_once(path, lines):
    content = path.read_text()
    missing = [line for line in lines if line not in content]
    if missing:
        path.write_text(content.rstrip() + "\n" + "\n".join(missing) + "\n")


append_once(
    ADDON / "models" / "__init__.py",
    [
        "from . import setup_compatibility",
        "from . import setup_readiness",
    ],
)
append_once(
    ADDON / "tests" / "__init__.py",
    ["from . import test_setup_consolidation"],
)
manifest_path = ADDON / "__manifest__.py"
manifest = manifest_path.read_text()
if '"views/setup_consolidation_views.xml"' not in manifest:
    marker = '"views/menu.xml",'
    if marker not in manifest:
        raise SystemExit("Could not find setup-flow manifest data insertion point")
    manifest = manifest.replace(
        marker,
        marker + '\n        "views/setup_consolidation_views.xml",',
        1,
    )
manifest = manifest.replace('"version": "19.0.1.0.0"', '"version": "19.0.2.0.0"')
manifest_path.write_text(manifest)
