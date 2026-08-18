#!/usr/bin/env python3
"""Partition Odoo CI output into actionable and expected diagnostics."""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil

TEST_MARKER = re.compile(r"\b(?:FAIL|ERROR):\s*(?P<name>[^\r\n]+)")
START_MARKER = re.compile(r"Starting\s+(?P<name>[\w.$]+\.[\w$]+)\s+\.\.\.")
EXCEPTION = re.compile(
    r"(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Failure))(?::\s*(?P<message>.*))?"
)
SOURCE = re.compile(
    r"File \"(?P<file>[^\"]+)\", line (?P<line>\d+), in (?P<method>[^\s]+)"
)
INFRA = re.compile(
    r"docker compose|postgres|connection refused|connection reset|timed out|timeout|"
    r"no such host|could not connect|apt-get|wget:|killed|out of memory|cannot start|"
    r"service .* failed|exit status [1-9]",
    re.I,
)


def clean(line: str) -> str:
    # Odoo prefixes every line with a timestamp/logger; retain the useful payload.
    return re.sub(r"^\d{4}-\d{2}-\d{2}[^ ]*\s+\d+\s+\w+\s+[^:]+:\s?", "", line).rstrip()


def failure_name(lines: list[str], index: int) -> str:
    for line in reversed(lines[max(0, index - 80) : index + 1]):
        match = TEST_MARKER.search(clean(line))
        if match:
            return match.group("name").strip()
    for line in reversed(lines[max(0, index - 30) : index + 1]):
        match = START_MARKER.search(clean(line))
        if match:
            return match.group("name")
    return "unknown test"


def traceback_block(lines: list[str], start: int) -> tuple[list[str], int]:
    block = [clean(lines[start])]
    index = start + 1
    while index < len(lines):
        payload = clean(lines[index])
        if index > start + 1 and (
            (payload and re.match(r"(?:FAIL|ERROR|ok|Ran)[: ]", payload))
            or (lines[index].strip() and re.match(r"\d{4}-\d{2}-\d{2}", lines[index]))
        ):
            break
        block.append(payload)
        index += 1
    while block and not block[-1]:
        block.pop()
    return block, index


def format_failure(name: str, block: list[str]) -> str:
    exception_type = "unknown exception"
    source = "unknown source"
    for line in reversed(block):
        match = EXCEPTION.search(line)
        if match:
            exception_type = match.group("type")
            break
    for line in reversed(block):
        match = SOURCE.search(line)
        if match:
            source = f"{match.group('file')}:{match.group('line')}"
            break
    method = name
    test_class = "unknown test class"
    class_match = re.match(r"(?P<method>[^ ]+)\s+\((?P<class>[^)]+)\)", name)
    if class_match:
        method = class_match.group("method")
        test_class = class_match.group("class")
    elif "." in name:
        test_class, method = name.rsplit(".", 1)
    return "\n".join(
        [
            f"Failing test class: {test_class}",
            f"Failing test method: {method}",
            f"Exception: {exception_type}",
            f"Source: {source}",
            "Final relevant traceback:",
            *block,
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_log", type=pathlib.Path)
    parser.add_argument("log_dir", type=pathlib.Path)
    args = parser.parse_args()
    raw_lines = args.raw_log.read_text(encoding="utf-8", errors="replace").splitlines()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.raw_log, args.log_dir / "full.log")

    failures: list[str] = []
    expected: list[str] = []
    infrastructure: list[str] = []
    seen_blocks: set[int] = set()
    for index, line in enumerate(raw_lines):
        payload = clean(line)
        if INFRA.search(payload):
            infrastructure.append(line)
        if "Traceback (most recent call last):" in payload and index not in seen_blocks:
            block, end = traceback_block(raw_lines, index)
            seen_blocks.update(range(index, end))
            name = failure_name(raw_lines, index)
            if any(
                TEST_MARKER.search(clean(candidate))
                for candidate in raw_lines[max(0, index - 80) : index + 1]
            ):
                failures.append(format_failure(name, block))
            else:
                expected.append("\n".join(block))
        elif re.search(r"(?:^|\s)(?:ERROR|FAIL):", payload) or re.search(
            r"test .* failed", payload, re.I
        ):
            if not INFRA.search(payload):
                expected.append(line)

    (args.log_dir / "test_failures.log").write_text(
        "\n\n".join(failures) + ("\n" if failures else ""), encoding="utf-8"
    )
    (args.log_dir / "expected_diagnostics.log").write_text(
        "\n".join(expected) + ("\n" if expected else ""), encoding="utf-8"
    )
    (args.log_dir / "infrastructure.log").write_text(
        "\n".join(dict.fromkeys(infrastructure)) + ("\n" if infrastructure else ""),
        encoding="utf-8",
    )
    for failure in failures:
        print(failure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
