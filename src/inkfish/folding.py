"""Language-agnostic code folding.

`find_fold_regions` returns regions identified by simple structural rules:

- ``.md``  — heading-based (`#`, `##`, ... starts a region ending before the
  next heading of equal or higher level).
- ``.html`` — tag-based (paired ``<tag>``/``</tag>``).
- ``.txt`` (default) — bracket-based (``{}``, ``[]``, ``(``…``)``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FoldRegion:
    start_line: int  # 0-indexed; this line is the header/opening and stays visible
    end_line: int    # 0-indexed; last hidden line
    kind: str        # "heading" | "tag" | "bracket"


def find_fold_regions(text: str, ext: str) -> list[FoldRegion]:
    ext = ext.lower()
    if ext == ".md":
        return _markdown_regions(text)
    if ext == ".html":
        return _html_regions(text)
    return _bracket_regions(text)


# ---- markdown ---------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s")


def _markdown_regions(text: str) -> list[FoldRegion]:
    lines = text.splitlines()
    headings: list[tuple[int, int]] = []  # (line_index, level)
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1))))
    regions: list[FoldRegion] = []
    for idx, (start, level) in enumerate(headings):
        end = len(lines) - 1
        for next_start, next_level in headings[idx + 1 :]:
            if next_level <= level:
                end = next_start - 1
                break
        if end > start:
            regions.append(FoldRegion(start, end, "heading"))
    return regions


# ---- html -------------------------------------------------------------------

_TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9-]*)[^>]*?(/?)\s*>")
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})


def _html_regions(text: str) -> list[FoldRegion]:
    lines = text.splitlines()
    stack: list[tuple[str, int]] = []  # (tag, line_index)
    regions: list[FoldRegion] = []
    for i, line in enumerate(lines):
        for m in _TAG_RE.finditer(line):
            closing, tag, self_closing = m.group(1), m.group(2).lower(), m.group(3)
            if tag in _VOID_TAGS or self_closing:
                continue
            if closing:
                for j in range(len(stack) - 1, -1, -1):
                    if stack[j][0] == tag:
                        opened_tag, opened_line = stack.pop(j)
                        if i > opened_line:
                            regions.append(FoldRegion(opened_line, i - 1, "tag"))
                        break
            else:
                stack.append((tag, i))
    return regions


# ---- brackets ---------------------------------------------------------------

_OPEN = "({["
_CLOSE = ")}]"
_MATCH = dict(zip(_CLOSE, _OPEN))


def _bracket_regions(text: str) -> list[FoldRegion]:
    lines = text.splitlines()
    stack: list[tuple[str, int]] = []  # (open_char, line_index)
    regions: list[FoldRegion] = []
    in_string: str | None = None
    for i, line in enumerate(lines):
        j = 0
        while j < len(line):
            c = line[j]
            if in_string is not None:
                if c == "\\":
                    j += 2
                    continue
                if c == in_string:
                    in_string = None
            elif c in ('"', "'"):
                in_string = c
            elif c in _OPEN:
                stack.append((c, i))
            elif c in _CLOSE:
                want = _MATCH[c]
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k][0] == want:
                        opened_char, opened_line = stack.pop(k)
                        if i > opened_line:
                            regions.append(FoldRegion(opened_line, i - 1, "bracket"))
                        break
            j += 1
        in_string = None  # strings don't span lines for this simple heuristic
    return regions
