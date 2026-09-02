#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
version = re.compile(r"(?<![A-Za-z0-9])" + "V" + r"2(?![A-Za-z0-9])", re.I)
delivery = re.compile(r"\b(?:phase|package)[\s_.-]*\d", re.I)
errors = []
for p in ROOT.rglob("*"):
    relative = p.relative_to(ROOT)
    if (
        p.is_file()
        and ".git" not in p.parts
        and "migrations" not in p.parts
        and (version.search(str(relative)) or delivery.search(str(relative)))
    ):
        errors.append(f"{relative}: obsolete delivery language in path")
    if (
        p.is_file()
        and ".git" not in p.parts
        and "migrations" not in p.parts
        and p.suffix
        in {".py", ".xml", ".md", ".json", ".yaml", ".yml", ".sh", ".js", ".scss"}
    ):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if version.search(line) or delivery.search(line):
                errors.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
if errors:
    print(
        "Obsolete delivery language found:\n- " + "\n- ".join(errors), file=sys.stderr
    )
    raise SystemExit(1)
print("Delivery language check passed.")
