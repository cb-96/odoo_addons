#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
service = (
    ROOT / "sports_federation_portal/models/task_projection_service.py"
).read_text()
if '_name = "federation.task.projection"' not in service:
    errors.append("missing single task projection service")
if "def _apply(" not in service:
    errors.append("task projection has no writer")
for path in ROOT.glob("sports_federation_*/models/*.py"):
    if path.name == "operation_task.py":
        continue
    txt = path.read_text()
    if "def _sync_specs(" in txt:
        errors.append("%s still owns _sync_specs" % path.relative_to(ROOT))
model = (ROOT / "sports_federation_portal/models/operation_task.py").read_text()
block = model[model.index("def _sync_specs(") : model.index("def _portal_get_domain")]
if "federation.task.projection" not in block:
    errors.append("legacy sync boundary does not delegate")
policy = (ROOT / "sports_federation_portal/task_policy.py").read_text()
for forbidden in (
    "competition_published",
    "roster_current",
    "lineup_approved",
    "no_gamedays",
    "season_completed",
):
    task_area = policy.split("STATUS_ONLY", 1)[0]
    if forbidden in task_area:
        errors.append("%s became a task type" % forbidden)
if errors:
    print("Task projection contract failed:\n- " + "\n- ".join(errors))
    sys.exit(1)
print("Task projection contract passed.")
