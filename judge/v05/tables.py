"""Tables in an answer, checked cell by cell against the result (code only).

A table row claims that a row with these values exists in the result. The row is located
by its key cells — cells whose text equals a text value of the result (a date, a document
number, a code) — and each numeric cell is compared with the result column its header
names. Only a positive mismatch is a false claim: a row that cannot be located, or a
header that names no result column, is undecided, never condemned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numbers import find_values, matches, parse_date
from .result import Result

MON3 = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def _norm(s) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


@dataclass
class TableCheck:
    rows: int = 0
    located: int = 0
    cells_checked: int = 0
    mismatches: list = field(default_factory=list)   # (row key, header, stated, true)


def _cells(line: str, code_block: bool) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        return [c.strip() for c in s.strip("|").split("|")]
    return [c.strip() for c in re.split(r"\s{2,}", s) if c.strip()]


def _header_columns(header: str, res: Result) -> list[int]:
    """Result columns a table header can name: exact, then containment either way."""
    h = _norm(header)
    if not h:
        return []
    exact = [i for i, c in enumerate(res.columns) if _norm(c) == h]
    if exact:
        return exact
    return [i for i, c in enumerate(res.columns) if h in _norm(c) or _norm(c) in h]


def check_tables(table_lines: list[tuple[str | None, str]], res: Result) -> TableCheck:
    out = TableCheck()
    text_index: dict[str, list[int]] = {}
    for ri, r in enumerate(res.full):
        for cell in r:
            if not isinstance(cell, (int, float)):
                text_index.setdefault(_norm(cell), []).append(ri)
    header: list[str] | None = None
    for heading, line in table_lines:
        if re.fullmatch(r"\|?[\s:|-]+\|?", line):          # markdown separator row
            continue
        cells = [c.lstrip("*").strip() for c in _cells(line, not line.startswith("|"))]
        if not cells:
            continue
        if header is None or (not any(re.search(r"\d", c) for c in cells)):
            header = cells
            continue
        out.rows += 1
        year = re.search(r"\b(20\d{2})\b", heading or "")
        keys = []
        for c in cells:
            k = c
            if year and _norm(c)[:3] in MON3 and len(_norm(c)) <= 9:
                k = f"{year.group(1)}-{MON3.index(_norm(c)[:3]) + 1:02d}"
            nk = _norm(k)
            if nk and nk in text_index:
                keys.append(nk)
        if not keys:
            continue
        candidates = set(text_index[keys[0]])
        for k in keys[1:]:
            candidates &= set(text_index[k])
        if len(candidates) != 1:
            continue
        row = res.full[candidates.pop()]
        out.located += 1
        for hi, c in enumerate(cells):
            if hi >= len(header) or _norm(c) in keys:
                continue
            vals = find_values(c)
            if len(vals) != 1 or parse_date(c):
                continue
            cols = [ci for ci in _header_columns(header[hi], res)
                    if isinstance(row[ci], (int, float)) and not isinstance(row[ci], bool)]
            if not cols:
                continue
            out.cells_checked += 1
            if not any(matches(vals[0], float(row[ci])) for ci in cols):
                out.mismatches.append((keys[0], header[hi], c, [row[ci] for ci in cols]))
    return out
