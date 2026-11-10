"""Load a production method for isolated tests without importing Odoo.

Dependencies must be supplied explicitly. Decorators are removed by default;
pass keep_decorators=True to test transaction wrappers. These tests do not
replace installed ORM, authorization, SQL, or browser integration tests.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_method(path, name, namespace=None, source=None, keep_decorators=False):
    tree = ast.parse(source if source is not None else (ROOT / path).read_text())
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise ValueError(
            "Expected exactly one production method %s in %s" % (name, path)
        )
    node = matches[0]
    if not keep_decorators:
        node.decorator_list = []
    scope = dict(namespace or {})
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(path), "exec"), scope)
    return scope[name]
