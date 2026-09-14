from pathlib import Path

root = Path(__file__).resolve().parent
addon = root / "sports_federation_setup_flow"

def append_once(path, text):
    content = path.read_text()
    if text.strip() not in content:
        path.write_text(content.rstrip() + "\n" + text)

append_once(addon / "models" / "__init__.py", "from . import competition_creation\nfrom . import competition_setup_enhancements\n")
append_once(addon / "wizards" / "__init__.py", "from . import competition_clone_wizard\nfrom . import gameday_setup_enhancements\n")
append_once(addon / "tests" / "__init__.py", "from . import test_setup_journey\n")
manifest = addon / "__manifest__.py"
content = manifest.read_text()
content = content.replace('"views/menu.xml",', '"views/menu.xml",\n        "security/setup_journey_access.csv",\n        "views/setup_journey_views.xml",')
manifest.write_text(content)
