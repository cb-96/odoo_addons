#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "sports_federation_format/models/fixture_result_bridge.py": [
        "logical_fixture_id",
        "_unique_logical_fixture",
        "_sync_logical_fixture_result",
    ],
    "sports_federation_format/services/fixture_materializer.py": [
        "FOR UPDATE",
        "operational_match_id",
        "logical_fixture_id",
    ],
    "sports_federation_format/models/stage_graph.py": [
        "operational_match_id",
        "bye_team_id",
        "Fixture results are read-only",
    ],
    "sports_federation_format/tests/test_fixture_result_ownership.py": [
        "test_playable_fixture_materializes_exactly_one_match",
        "test_bye_is_structural",
    ],
}
errors = []
for rel, tokens in checks.items():
    path = ROOT / rel
    if not path.is_file():
        errors.append(f"missing {rel}")
        continue
    text = path.read_text(encoding="utf-8")
    errors.extend(f"{rel}: missing {token}" for token in tokens if token not in text)
engine = (ROOT / "sports_federation_format/services/stage_graph_engine.py").read_text(
    encoding="utf-8"
)
for token in ('"home_score": 1', '"away_score": 1'):
    if token in engine:
        errors.append(f"fabricated bye result remains: {token}")
if errors:
    print("Phase 1 fixture contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Phase 1 fixture contract passed.")
