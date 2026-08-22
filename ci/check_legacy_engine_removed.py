#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
TERMS=("sports_federation_competition_engine","competition_workspace","Competition Workspace")
SCAN_ROOTS=(ROOT/".github",ROOT/"ci",ROOT/"scripts",ROOT/"docs",ROOT/"_workflows")
SCAN_FILES=(ROOT/"README.md",ROOT/"CONTRIBUTING.md",ROOT/"ROADMAP.md",ROOT/"MODULE_OWNERS.yaml",ROOT/"TECHNICAL_NOTE.md")
SUFFIXES={".py",".xml",".js",".sh",".bash",".md",".yml",".yaml",".json",".txt"}
errors=[]
if (ROOT/"sports_federation_competition_engine").exists():errors.append("legacy addon directory still exists")
files=list(SCAN_FILES)
for base in SCAN_ROOTS:
 if base.exists():files.extend(path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in SUFFIXES)
for path in files:
 if not path.exists() or path.resolve()==Path(__file__).resolve():continue
 text=path.read_text(encoding="utf-8",errors="replace")
 for term in TERMS:
  if term in text:errors.append(f"{path.relative_to(ROOT)} contains {term}")
for manifest in ROOT.glob("sports_federation_*/__manifest__.py"):
 if "sports_federation_competition_engine" in manifest.read_text(encoding="utf-8"):errors.append(f"dependency remains in {manifest.relative_to(ROOT)}")
if errors:
 print("Legacy engine removal check failed:");[print(f"- {error}") for error in sorted(set(errors))];sys.exit(1)
print("Legacy competition engine is absent from runtime, CI and active documentation.")
