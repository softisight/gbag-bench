"""Step 6 — the facts a unit may state, by family, computed on a scope (code only).

`check(family, unit, res, scope, cols, reference)` returns (status, true_values, detail):
  "match"    - the figure equals one of the family's facts at this scope;
  "mismatch" - facts were computed and none equals the figure;
  "none"     - the family computes no fact here (no column, `place`, `other`...).
Whether a mismatch becomes a condemnation is decided in decide.py, never here.
"""
from __future__ import annotations

import re
import statistics

from judge.v05.numbers import Value, find_dates, find_values, matches, parts_match, words_to_digits
from judge.v05.result import Result

PARTIAL = re.compile(r"\b(top \w+|first \d+|together|combined|\d[\d,.]*\s+of the|out of|account(?:s|ed)? for|"
                     r"make up|between them)\b", re.I)
ROWS_WORD = re.compile(r"\b(rows?|lines?|records?|entries|movements|postings|transactions|days)\s+(?:shown|displayed|returned|in (?:the|this|total))", re.I)
ABOVE = re.compile(r"\b(above|over|more than|exceed(?:s|ed|ing)?|greater than|at least|beyond)\s*[~≈]?\s*$", re.I)
BELOW = re.compile(r"\b(below|under|less than|at most|no more than|up to)\s*[~≈]?\s*$", re.I)


def _num(c) -> bool:
    return isinstance(c, (int, float)) and not isinstance(c, bool)


def comparator(unit) -> str | None:
    i = unit.sentence.find(unit.raw)
    if i <= 0:
        return None
    before = unit.sentence[max(0, i - 24):i]
    return ">" if ABOVE.search(before) else "<" if BELOW.search(before) else None


def _fig_matches(unit, true: float) -> bool:
    v, cmp = unit.figure, comparator(unit)
    if cmp == ">" and true >= v.value:
        return True
    if cmp == "<" and true <= v.value:
        return True
    return matches(v, float(true))


def _date_matches(unit, cell) -> bool:
    return bool(find_dates(str(cell))) and parts_match(unit.date, cell)


def _numeric_cols(res: Result, cols: list[int] | None) -> list[int]:
    if cols:
        return cols
    return [i for i in range(len(res.columns)) if any(_num(r[i]) for r in res.full[:50])]


def _date_cols(res: Result) -> list[int]:
    return [i for i in range(len(res.columns)) if res.full and find_dates(str(res.full[0][i]))]


def _other_figures(unit) -> list[float]:
    return [v.value for v in find_values(words_to_digits(unit.sentence)) if v.raw != unit.raw]


def check(family: str, unit, res: Result, scope: str, cols: list[int] | None, reference: str | None):
    rows = res.rows(scope)
    if not rows or family in ("place", "other", None):
        return "none", [], f"family {family!r} states no checkable fact"

    # ---- a date unit: extremes and ends of date columns, or a date that exists
    if unit.date:
        dcols = _date_cols(res)
        if not dcols:
            return "none", [], "no date column"
        # A date next to "the highest" says WHEN a value peaks: it locates, it is not the
        # maximum of the dates. Only first/last/cell are judged on a date.
        vals = {"last": lambda c: [r[c] for r in rows[-1:]], "first": lambda c: [r[c] for r in rows[:1]],
                "cell": lambda c: [r[c] for r in rows]}.get(family)
        if vals is None:
            return "none", [], f"family {family!r} does not apply to a date"
        trues = [v for c in dcols for v in vals(c)]
        hit = any(_date_matches(unit, t) for t in trues)
        return ("match" if hit else "mismatch"), trues[:3], f"{family} of the date column(s)"

    if unit.figure is None:
        return "none", [], "no figure"
    ncols = _numeric_cols(res, cols)
    series = {c: [float(r[c]) for r in rows if _num(r[c])] for c in ncols}
    series = {c: s for c, s in series.items() if s}
    if not series and family != "count":
        return "none", [], "no numeric column"
    trues: list[float] = []

    if family == "cell":
        # a value is a value wherever it sits: any numeric column (the column choice only
        # matters for families that aggregate)
        trues = [float(c) for r in rows for c in r if _num(c)]
    elif family == "sum":
        partial = PARTIAL.search(unit.sentence)
        for s in series.values():
            trues += [round(sum(s), 2), s[-1]]
            if partial:
                # "the top three account for 1,307": a prefix sum, ONLY when the sentence says
                # the sum is partial — otherwise a window's running total would pass as "a
                # partial sum" of the data, which is exactly the failure GBAG measures
                acc = 0.0
                for x in s:
                    acc += x
                    trues.append(round(acc, 2))
    elif family in ("maximum", "minimum"):
        trues = [(max if family == "maximum" else min)(s) for s in series.values()]
    elif family in ("last", "first"):
        trues = [s[-1] if family == "last" else s[0] for s in series.values()]
    elif family == "ratio":
        others = _other_figures(unit)
        refs = [reference] if reference else ["second_largest", "median", "mean", "named_value"]
        for s in series.values():
            num = max(s)
            distinct = sorted(set(s), reverse=True)
            for ref in refs:
                dens = {"second_largest": distinct[1:2], "median": [statistics.median(s)],
                        "mean": [statistics.mean(s)], "named_value": others}.get(ref, [])
                trues += [round(num / d, 3) for d in dens if d]
        # a ratio said "roughly N times" is compared loosely
        v = unit.figure
        unit = type(unit)(unit.idx, unit.raw, Value(v.raw, v.value, v.decimals, v.unit, True),
                          None, unit.sentence, unit.context, unit.places)
    elif family == "share":
        n = len(rows)
        others = _other_figures(unit)
        for s in series.values():
            for lo in others:
                for hi in others:
                    if lo < hi:
                        trues.append(sum(1 for x in s if lo <= x <= hi) / len(s))
        trues += [o / n for o in others if 0 < o <= n]
        trues = [t * 100 if unit.figure.unit == "%" else t for t in trues]
    elif family == "count":
        trues = [float(len(rows))]
        words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9-]+", unit.sentence) if len(w) >= 2}
        tcols = [i for i in range(len(res.columns)) if res.full and isinstance(res.full[0][i], str)]
        subset_found = False
        for w in words:
            sel = [r for r in rows if any(w in str(r[i]).lower() for i in tcols)]
            if 0 < len(sel) < len(rows):
                subset_found = True
                trues.append(float(len(sel)))
                if len(sel) == 1:                     # an aggregated row naming it
                    trues += [float(c) for c in sel[0] if _num(c)]
        if len(rows) == 1:
            subset_found = True
            trues += [float(c) for c in rows[0] if _num(c)]
        if not subset_found and not ROWS_WORD.search(unit.sentence):
            # "the six flagged payroll entries": a subset the code cannot compute. Refutable
            # only for a plain count of rows, or of a subset a word of the sentence selects.
            hit = any(_fig_matches(unit, t) for t in trues)
            return ("match" if hit else "none"), trues[:1], "count of a subset the code cannot compute"
    elif family == "change":
        for s in series.values():
            pairs = list(zip(s, s[1:])) + ([(s[0], s[-1])] if len(s) > 1 else [])
            for a, b in pairs:
                trues.append(abs(round(b - a, 2)))
                if a:
                    trues.append(abs(round(100 * (b - a) / abs(a), 1)))
        # the result may already hold the changes (a change or % column)
        trues += [abs(float(c)) for r in rows for c in r if _num(c)]
        # direction is carried by words ("below", "down"): v0.6 compares magnitudes
        v = unit.figure
        unit = type(unit)(unit.idx, unit.raw, Value(v.raw, abs(v.value), v.decimals, v.unit, v.approximate),
                          None, unit.sentence, unit.context, unit.places)
    else:
        return "none", [], f"unknown family {family!r}"

    if not trues:
        return "none", [], "no fact computed"
    hit = any(_fig_matches(unit, t) for t in trues)
    shown = trues[:3] if not hit else [t for t in trues if _fig_matches(unit, t)][:1]
    return ("match" if hit else "mismatch"), shown, f"{family} over {len(series) or 1} column(s)"


_DM = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b\.?"
                 r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?\b", re.I)
_M = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
                r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b")


def _places(unit) -> list[str]:
    """EVERY place the sentence names: full dates, day-month, and month-only mentions
    ("mid-May, late July ... 26 Nov") — v0.5's reader stops at the first format it finds."""
    if not unit.places:
        return []
    s = unit.sentence
    out = list(find_dates(s)) + [m.group(0) for m in _DM.finditer(s)]
    covered = " ".join(out)
    out += [m.group(0) for m in _M.finditer(s) if m.group(0) not in covered]
    return out or unit.places


def located_rows(unit, res: Result, scope: str) -> list[tuple]:
    """Rows the sentence's places (dates, periods) point at."""
    rows = res.rows(scope)
    places = _places(unit)
    if not places:
        return []
    return [r for r in rows if any(parts_match(p, c) for p in places for c in r if find_dates(str(c)))]
