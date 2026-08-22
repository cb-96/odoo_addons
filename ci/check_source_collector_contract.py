#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
collector=ROOT/"source_collector.py"
errors=[]
if not collector.is_file(): errors.append("source_collector.py is missing")
else:
 text=collector.read_text(encoding="utf-8")
 for token in ('".sh"','".bash"','source_collector.py'):
  if token not in text: errors.append(f"collector contract missing {token}")
required=["ci/run_tests.sh","ci/run_odoo_tests.sh","scripts/ci/run_rc_validation.sh","source_collector.py"]
for item in required:
 if not (ROOT/item).is_file(): errors.append(f"required review source missing: {item}")
if errors:
 print("Source collector contract failed:");[print(f"- {e}") for e in errors];sys.exit(1)
print("Source collector contract passed.")
