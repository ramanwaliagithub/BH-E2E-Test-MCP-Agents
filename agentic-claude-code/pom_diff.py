"""Turn a healed locator value into a reviewable diff against a POM file.

Intentionally duplicated from (not imported from) agentic/agents/locator_healer.py's
find_locator/build_healed_line/build_diff — same small amount of logic, kept as
its own copy so this folder has zero code dependency on agentic/. The two
"brains" (a standalone Claude API call vs. Claude Code itself) are meant to be
swappable without ever sharing state or imports.

Never writes to the POM file. Only prints a unified diff for a human to review.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocatorSite:
    const_name: str
    lineno: int
    line: str
    current_value: str


def find_locator(source: str, class_name: str, const_name: str) -> LocatorSite:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            if stmt.targets[0].id != const_name:
                continue
            if not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str):
                continue
            return LocatorSite(
                const_name=const_name,
                lineno=stmt.lineno,
                line=lines[stmt.lineno - 1],
                current_value=stmt.value.value,
            )

    raise ValueError(f"Could not find '{const_name}' as a string constant in class '{class_name}'")


def build_healed_line(original_line: str, const_name: str, new_value: str) -> str:
    match = re.match(
        rf"^(?P<indent>\s*){re.escape(const_name)}(?P<sep>\s*=\s*)(?P<quote>['\"])(?P<old>.*)(?P=quote)(?P<trail>\s*)$",
        original_line,
    )
    if not match:
        raise ValueError(f"Line does not match expected 'CONST = \"...\"' shape: {original_line!r}")

    quote = match["quote"]
    if quote in new_value:
        quote = '"' if new_value.count('"') < new_value.count("'") else "'"

    newline = "\n" if original_line.endswith("\n") else ""
    return f"{match['indent']}{const_name}{match['sep']}{quote}{new_value}{quote}{match['trail'].rstrip(chr(10))}{newline}"


def build_diff(pom_path: Path, source: str, site: LocatorSite, new_value: str) -> str:
    old_lines = source.splitlines(keepends=True)
    new_lines = old_lines.copy()
    new_lines[site.lineno - 1] = build_healed_line(site.line, site.const_name, new_value)
    diff_lines = difflib.unified_diff(
        old_lines, new_lines, fromfile=str(pom_path), tofile=str(pom_path), lineterm=""
    )
    return "\n".join(line.rstrip("\n") for line in diff_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a reviewable diff for a healed POM locator")
    parser.add_argument("--pom", required=True, type=Path)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--locator", required=True)
    parser.add_argument("--new-value", required=True)
    args = parser.parse_args()

    source = args.pom.read_text()
    site = find_locator(source, args.class_name, args.locator)

    if site.current_value == args.new_value:
        print(f"No change needed — '{args.locator}' already equals {args.new_value!r}")
        return

    print(build_diff(args.pom, source, site, args.new_value))


if __name__ == "__main__":
    main()
