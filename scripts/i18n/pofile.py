"""Minimal gettext PO reader and writer for the translation tooling.

Only the standard library is used, so the CI checks run without extra
packages. It covers what Odoo exports and Weblate writes: translator and
reference comments, flags, single and multi-line ``msgid``/``msgstr``.
Obsolete entries (``#~``) are ignored when reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), text)


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


@dataclass
class Entry:
    msgid: str
    msgstr: str = ""
    comments: list[str] = field(default_factory=list)  # "#." lines
    references: list[str] = field(default_factory=list)  # "#:" lines
    flags: list[str] = field(default_factory=list)  # "#," values
    line: int = 0

    @property
    def translated(self) -> bool:
        return bool(self.msgstr)


@dataclass
class Catalog:
    header: Entry
    entries: list[Entry]
    duplicates: list[str] = field(default_factory=list)

    def header_value(self, name: str) -> str:
        for line in self.header.msgstr.split("\n"):
            key, _, value = line.partition(":")
            if key.strip().lower() == name.lower():
                return value.strip()
        return ""

    def by_msgid(self) -> dict[str, Entry]:
        return {entry.msgid: entry for entry in self.entries}


class PoError(ValueError):
    pass


def read(path: Path | str) -> Catalog:
    path = Path(path)
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    entries: list[Entry] = []
    current = Entry(msgid="")
    key = None
    started = False

    def finish():
        nonlocal current, key, started
        if started:
            entries.append(current)
        current = Entry(msgid="")
        key = None
        started = False

    for number, raw in enumerate(text.split("\n") + [""], start=1):
        line = raw.strip()
        if not line:
            if key == "msgstr":
                finish()
            continue
        if line.startswith("#~"):
            continue
        if line.startswith("#"):
            if key == "msgstr":
                finish()
            if line.startswith("#."):
                current.comments.append(line[2:].strip())
            elif line.startswith("#:"):
                current.references.extend(line[2:].split())
            elif line.startswith("#,"):
                current.flags.extend(f.strip() for f in line[2:].split(","))
            continue
        match = re.match(
            r'^(msgctxt|msgid|msgid_plural|msgstr(?:\[\d+\])?)\s+"(.*)"$', line
        )
        if match:
            name, value = match.groups()
            if name == "msgid" and key == "msgstr":
                finish()
            if name == "msgid":
                started = True
                current.line = number
            if name in ("msgctxt", "msgid_plural") or name.startswith("msgstr["):
                raise PoError("%s:%s: %s is not supported" % (path, number, name))
            key = name
            setattr(current, key, _unescape(value))
            continue
        match = re.match(r'^"(.*)"$', line)
        if match and key:
            setattr(current, key, getattr(current, key) + _unescape(match.group(1)))
            continue
        raise PoError("%s:%s: cannot parse %r" % (path, number, raw))
    finish()

    header = Entry(msgid="")
    body = []
    seen = set()
    duplicates = []
    for entry in entries:
        if entry.msgid == "":
            header = entry
            continue
        if entry.msgid in seen:
            duplicates.append(entry.msgid)
            continue
        seen.add(entry.msgid)
        body.append(entry)
    return Catalog(header=header, entries=body, duplicates=duplicates)


def _field(name: str, value: str) -> str:
    if "\n" not in value:
        return '%s "%s"\n' % (name, _escape(value))
    parts = value.split("\n")
    out = '%s ""\n' % name
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if last and not part:
            break
        out += '"%s%s"\n' % (_escape(part), "" if last else "\\n")
    return out


def write(catalog: Catalog, path: Path | str) -> None:
    out = []
    header = catalog.header
    for comment in header.comments:
        out.append("# %s\n" % comment if comment else "#\n")
    out.append(_field("msgid", ""))
    out.append(_field("msgstr", header.msgstr))
    out.append("\n")
    for entry in catalog.entries:
        for comment in entry.comments:
            out.append("#. %s\n" % comment)
        for reference in entry.references:
            out.append("#: %s\n" % reference)
        if entry.flags:
            out.append("#, %s\n" % ", ".join(entry.flags))
        out.append(_field("msgid", entry.msgid))
        out.append(_field("msgstr", entry.msgstr))
        out.append("\n")
    Path(path).write_text("".join(out).rstrip("\n") + "\n", encoding="utf-8")


def header_text(language: str, module: str) -> str:
    return (
        "Project-Id-Version: Odoo Server 19.0\n"
        "Report-Msgid-Bugs-To: \n"
        "Last-Translator: \n"
        "Language-Team: \n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: \n"
        "Language: %s\n"
        "Plural-Forms: \n" % language
    )


# --------------------------------------------------------------------------
# Consistency between a source text and its translation
# --------------------------------------------------------------------------

_PLACEHOLDER = re.compile(
    r"%\([A-Za-z_][A-Za-z0-9_]*\)[sdrf]|%[sdrf]|\{[A-Za-z_][A-Za-z0-9_]*\}"
)
_TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9_.-]*)\b[^>]*?/?>")


def placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER.findall(text.replace("%%", "")))


def tags(text: str) -> list[str]:
    """Element names in order of appearance, closing tags prefixed with '/'."""
    result = []
    for match in _TAG.finditer(text):
        raw = match.group(0)
        name = match.group(1)
        if raw.startswith("</"):
            result.append("/" + name)
        elif raw.endswith("/>"):
            result.append(name + "/")
        else:
            result.append(name)
    return result


# Odoo loads a code translation only when the entry carries the marker for
# its runtime: "#. odoo-python" for Python, "#. odoo-javascript" for web
# assets. Without it the msgstr is silently ignored and users see English.
PYTHON_MARKER = "odoo-python"
JAVASCRIPT_MARKER = "odoo-javascript"


def code_markers(entry: Entry) -> list[str]:
    """Markers Odoo needs for the code references of ``entry``."""
    markers = set()
    for reference in entry.references:
        match = re.match(r"code:addons/\w+/(\S+?)(?::\d+)?$", reference)
        if not match:
            continue
        if match.group(1).endswith(".py"):
            markers.add(PYTHON_MARKER)
        elif "/static/" in match.group(1):
            markers.add(JAVASCRIPT_MARKER)
    return sorted(markers)


def add_code_markers(entry: Entry) -> Entry:
    for marker in code_markers(entry):
        if marker not in entry.comments:
            entry.comments.append(marker)
    return entry


def problems(entry: Entry) -> list[str]:
    """Reasons why a translation would break the page or the message."""
    missing = [m for m in code_markers(entry) if m not in entry.comments]
    found = [
        "code translation lacks '#. %s'; Odoo ignores it" % marker for marker in missing
    ]
    if not entry.msgstr:
        return found
    if placeholders(entry.msgid) != placeholders(entry.msgstr):
        found.append(
            "placeholders differ: %s vs %s"
            % (placeholders(entry.msgid), placeholders(entry.msgstr))
        )
    if sorted(tags(entry.msgid)) != sorted(tags(entry.msgstr)):
        found.append(
            "markup differs: %s vs %s" % (tags(entry.msgid), tags(entry.msgstr))
        )
    return found
