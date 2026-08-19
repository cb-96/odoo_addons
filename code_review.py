from pathlib import Path

ROOT = Path(".").resolve()
OUTPUT = ROOT / "odoo_addons_code_review.txt"

INCLUDED_SUFFIXES = {
    ".py",
    ".xml",
    ".js",
    ".ts",
    ".scss",
    ".css",
    ".json",
    ".csv",
    ".md",
    ".rst",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sql",
    ".sh",
}

INCLUDED_NAMES = {
    "Dockerfile",
    "Makefile",
    ".gitignore",
    ".dockerignore",
    "requirements.txt",
    "requirements-dev.txt",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

EXCLUDED_PARTS = {
    ".git",
    ".github_cache",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "filestore",
    "sessions",
    "data",
}

MAX_FILE_SIZE = 1_000_000

files = []

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue

    relative = path.relative_to(ROOT)

    if any(part in EXCLUDED_PARTS for part in relative.parts):
        continue

    if path.name == OUTPUT.name:
        continue

    if path.suffix.lower() not in INCLUDED_SUFFIXES and path.name not in INCLUDED_NAMES:
        continue

    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            continue
    except OSError:
        continue

    files.append(path)

files.sort(key=lambda path: str(path.relative_to(ROOT)).lower())

with OUTPUT.open("w", encoding="utf-8") as output:
    output.write("# Odoo Addons Code Review Bundle\n\n")
    output.write(f"Repository root: {ROOT.name}\n")
    output.write(f"Files included: {len(files)}\n\n")

    output.write("## Repository tree\n\n")
    for path in files:
        output.write(f"- {path.relative_to(ROOT)}\n")

    output.write("\n\n")

    for path in files:
        relative = path.relative_to(ROOT)
        output.write("\n")
        output.write("=" * 100)
        output.write("\n")
        output.write(f"FILE: {relative}\n")
        output.write("=" * 100)
        output.write("\n\n")

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            output.write(f"[Unable to read file: {exc}]\n")
            continue

        output.write(content)

        if not content.endswith("\n"):
            output.write("\n")

print(f"Created: {OUTPUT}")
print(f"Included files: {len(files)}")
print(f"Size: {OUTPUT.stat().st_size / 1024 / 1024:.2f} MB")
