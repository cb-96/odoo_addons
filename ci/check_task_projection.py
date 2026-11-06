#!/usr/bin/env python3
"""Structural checks for read-only collectors and one synchronization writer.

Behavior is covered by ci.test_task_projection and the portal ORM tests.
"""
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODELS = Path("sports_federation_portal/models")


def violations(root=ROOT):
    errors = []
    sync_owners = []
    for filename in (
        "task_projection.py", "journey_operation_task.py",
        "task_projection_service.py", "operation_task.py",
    ):
        path = MODELS / filename
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == "sync_for_user":
                    sync_owners.append(filename)
                if node.name in {"_sync_specs", "_sync_for_user_legacy", "_sync_review_handoffs"}:
                    errors.append(f"{path}: obsolete synchronization method {node.name}")
                readonly = node.name.startswith("_collect_") or node.name == "_project_task_specs"
                for call in ast.walk(node):
                    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                        continue
                    method = call.func.attr
                    if readonly and method in {"create", "write", "unlink", "_apply", "synchronize"}:
                        errors.append(f"{path}: collector {node.name} calls {method}")
                    if filename == "task_projection_service.py" and method in {"create", "write", "unlink"} and node.name != "_apply":
                        errors.append(f"{path}: synchronization write outside _apply")
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Call)
                            and isinstance(target.value.func, ast.Name)
                            and target.value.func.id == "type"):
                        errors.append(f"{path}: shared-class method replacement")
    if sync_owners != ["task_projection.py"]:
        errors.append("sync_for_user must have one owner in task_projection.py")
    return errors


def main():
    errors = violations()
    if errors:
        print("Task projection contract failed:\n- " + "\n- ".join(errors))
        return 1
    print("Task projection structure passed; run behavioral and ORM tests separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
