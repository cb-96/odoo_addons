#!/usr/bin/env python3
"""Catch unreadable text colours in addon SCSS.

Two mistakes produced white text on a white Competition Hub card:

1. Odoo does not define ``--body-bg``, ``--border-color``, ``--text-muted``,
   ``--o-brand-primary`` or ``--o-view-background-color``; their light
   fallbacks are used in every theme, including dark mode.
2. A second rule for the same selector replaced the dark background but kept
   the white text from the first rule.

The check flattens nested SCSS, merges declarations per selector in source
order (as the cascade does for equal specificity) and fails when the final
rule pairs a light text colour with a light or themed surface.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
UNDEFINED_VARS = re.compile(
    r"var\(--(body-bg|border-color|text-muted|o-brand-primary|o-view-background-color)\b"
)
LIGHT_TEXT = re.compile(
    r"^(#fff(fff)?|white|var\(--bs-white\)|rgba?\(255,\s*255,\s*255)", re.I
)
LIGHT_SURFACE = re.compile(
    r"^(#fff(fff)?|white|#f[0-9a-f]{5}|var\(--bs-(body-bg|white|light|tertiary-bg|secondary-bg)\)"
    r"|var\(--[\w-]+,\s*(#fff(fff)?|white|#f[0-9a-f]{5})\))",
    re.I,
)


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)//.*$", "", text)


def rules(text):
    """Yield (selector path, {property: value}) in source order."""
    stack, buffer = [], ""
    declarations = [{}]
    for char in _strip_comments(text):
        if char == "{":
            stack.append(" ".join(buffer.split()))
            declarations.append({})
            buffer = ""
        elif char == "}":
            for chunk in buffer.split(";"):
                if ":" in chunk:
                    name, value = chunk.split(":", 1)
                    declarations[-1][name.strip()] = value.strip()
            buffer = ""
            if stack:
                selector = stack.pop()
                props = declarations.pop()
                if not selector.startswith("@"):
                    yield tuple(stack + [selector]), props
        elif char == ";":
            if ":" in buffer:
                name, value = buffer.split(":", 1)
                declarations[-1][name.strip()] = value.strip()
            buffer = ""
        else:
            buffer += char


def check_file(path):
    errors = []
    text = path.read_text(encoding="utf-8")
    for match in UNDEFINED_VARS.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(
            f"{path.relative_to(ROOT)}:{line}: --{match.group(1)} is not an Odoo theme variable; use the --bs-* equivalent"
        )
    merged = {}
    for selector, props in rules(text):
        if any(part.startswith("@") for part in selector):
            continue
        merged.setdefault(selector, {}).update(props)
    for selector, props in merged.items():
        colour = props.get("color", "").replace("!important", "").strip()
        surface = (
            (props.get("background-color") or props.get("background") or "")
            .replace("!important", "")
            .strip()
        )
        if (
            colour
            and surface
            and LIGHT_TEXT.match(colour)
            and LIGHT_SURFACE.match(surface)
        ):
            errors.append(
                f"{path.relative_to(ROOT)}: '{' '.join(selector)}' ends with light text ({colour}) on a light surface ({surface})"
            )
    return errors


def main():
    errors = []
    for path in sorted(ROOT.glob("sports_federation_*/static/src/**/*.scss")):
        errors.extend(check_file(path))
    if errors:
        print("SCSS contrast check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("SCSS contrast check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
