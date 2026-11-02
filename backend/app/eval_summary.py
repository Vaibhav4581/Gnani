"""The headline of eval/RESULTS.md for the home page: the run line, the whole-clip score,
the first table (quiet vs noisy vs phone line) and the caveat about synthetic voices.

Read on request, so a new eval run shows up without touching the page.
"""
import re
from pathlib import Path
from typing import Optional


def _plain(text: str) -> str:
    """Markdown emphasis and code marks off: "**whole clip right**" -> "whole clip right"."""
    return re.sub(r"\*\*|`", "", text).strip()


def _cells(line: str) -> list[str]:
    return [_plain(c) for c in line.strip().strip("|").split("|")]


def first_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Header and rows of the first Markdown table, or ([], [])."""
    for i, line in enumerate(lines):
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                rows.append(_cells(row))
            return _cells(line), rows
    return [], []


def summary(path: Path) -> Optional[dict]:
    """None when the results file doesn't exist."""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    run = next((_plain(l) for l in lines if l.startswith("Run ")), None)
    headline = next((_plain(l) for l in lines if l.startswith("**Whole clips right")), None)
    caveat = next((_plain(l.lstrip("> ")) for l in lines if l.startswith(">")), None)
    columns, rows = first_table(lines)
    return {"run": run, "headline": headline, "columns": columns, "rows": rows, "caveat": caveat}
