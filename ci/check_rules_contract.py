#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "sports_federation_rules/services/standings.py": [
        "def points_map",
        "def tie_breaks",
        "def rank",
        "head_to_head",
    ],
    "sports_federation_format/services/stage_graph_engine.py": [
        "federation.standings.rules",
        "_get_effective_rule_set",
    ],
    "sports_federation_standings/models/standing.py": ["federation.standings.rules"],
}
errors = []
for rel, tokens in checks.items():
    path = ROOT / rel
    if not path.is_file():
        errors.append(f"missing {rel}")
        continue
    text = path.read_text(encoding="utf-8")
    errors.extend(f"{rel}: missing {token}" for token in tokens if token not in text)
legacy = (ROOT / "sports_federation_format/services/stage_graph_engine.py").read_text(
    encoding="utf-8"
)
for token in (
    'h["points"] += 3',
    'a["points"] += 3',
    'h["points"] += 1',
    'a["points"] += 1',
):
    if token in legacy:
        errors.append(f"Format still hard-codes scoring: {token}")
if errors:
    print("Rules contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Rules contract passed.")
