"""Step 3 — compute the true value of a fact sheet at a scope (code only).

`evaluate(sheet, result, scope)` returns an Outcome: True / False / None (undecided) with
the true value it computed. None is returned whenever the sheet cannot be evaluated on
the result — unknown column, unreadable figure, type `other` — never a guess.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .numbers import Value, find_values, matches, parse_date, parse_value
from .result import Result

# what a quantifier word commits to, as a share of rows
QUANT_TEST = {
    "all": lambda f: f >= 0.99,
    "almost_all": lambda f: f >= 0.80,
    "most": lambda f: f > 0.50,
    "majority": lambda f: f > 0.50,
    "half": lambda f: 0.40 <= f <= 0.60,
    "few": lambda f: f < 0.20,
    "none": lambda f: f <= 0.01,
}


@dataclass
class Outcome:
    holds: bool | None
    true_value: object = None
    detail: str = ""


def _undecided(why: str) -> Outcome:
    return Outcome(None, None, why)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _cell_matches(stated: str, cell) -> bool:
    """A stated label/date/number against one result cell."""
    if cell is None or stated is None:
        return False
    d_st, d_cell = parse_date(stated), parse_date(str(cell))
    if d_st and d_cell:
        return d_cell.startswith(d_st) or d_st.startswith(d_cell)
    if _is_num(cell):
        v = parse_value(stated)
        return v is not None and matches(v, float(cell))
    norm = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
    return norm(stated) == norm(cell) and norm(stated) != ""


def _value_matches(stated: str, true) -> bool | None:
    if true is None:
        return None
    if not _is_num(true):
        d_st, d_true = parse_date(stated), parse_date(str(true))
        if d_st and d_true:
            return d_true.startswith(d_st) or d_st.startswith(d_true)
        return _cell_matches(stated, true)
    v = parse_value(stated)
    if v is None:
        return None
    return matches(v, float(true))


def _column(sheet, res: Result) -> int | None:
    return res.col(sheet.column) if sheet.column else None


def _sortable(v):
    return float(v) if _is_num(v) else str(v)


def evaluate(sheet, res: Result, scope: str) -> Outcome:
    rows = res.rows(scope)
    if not rows:
        return _undecided("empty result")
    t = sheet.type
    ci = _column(sheet, res)

    if t == "count":
        sel = rows
        if sheet.filter_column:
            fi = res.col(sheet.filter_column)
            if fi is None:
                return _undecided(f"filter column {sheet.filter_column!r} not in the result")
            fv = (sheet.filter_value or "").lower()
            op = sheet.filter_op or "eq"
            test = {"eq": lambda c: str(c).lower() == fv,
                    "startswith": lambda c: str(c).lower().startswith(fv),
                    "contains": lambda c: fv in str(c).lower()}[op]
            sel = [r for r in rows if test(r[fi])]
        n = len(sel)
        ok = _value_matches(sheet.value or "", n)
        return Outcome(ok, n, f"{n} matching rows")

    if ci is None:
        return _undecided(f"column {sheet.column!r} not in the result")
    cells = [r[ci] for r in rows]

    if t == "total":
        nums = [float(c) for c in cells if _is_num(c)]
        if not nums:
            return _undecided("no numeric cell")
        monotone = all(b >= a for a, b in zip(nums, nums[1:]))
        cumulative = monotone and ("cum" in res.columns[ci].lower() or "running" in res.columns[ci].lower())
        true = nums[-1] if cumulative else round(sum(nums), 2)
        return Outcome(_value_matches(sheet.value or "", true), true,
                       "final value of a running total" if cumulative else "sum of the column")

    if t in ("extreme", "end_value"):
        if t == "extreme":
            if sheet.which not in ("max", "min"):
                return _undecided("extreme without max/min")
            keyed = [(c, r) for c, r in zip(cells, rows) if c is not None]
            best = (max if sheet.which == "max" else min)(keyed, key=lambda cr: _sortable(cr[0]))[0]
            hit_rows = [r for c, r in keyed if c == best]
        else:
            if sheet.which not in ("first", "last"):
                return _undecided("end_value without first/last")
            r = rows[0] if sheet.which == "first" else rows[-1]
            best, hit_rows = r[ci], [r]
        ok = True
        if sheet.value:
            ok = _value_matches(sheet.value, best)
        if ok and sheet.at:
            ok = any(_cell_matches(sheet.at, cell) for r in hit_rows for cell in r)
        return Outcome(ok, best, f"{sheet.which} = {best!r}")

    if t == "share":
        nums = [float(c) for c in cells if _is_num(c)]
        if not nums:
            return _undecided("no numeric cell")
        lo = parse_value(sheet.low) if sheet.low else None
        hi = parse_value(sheet.high) if sheet.high else None
        if lo is None and hi is None:
            return _undecided("share without a range")
        inside = [x for x in nums if (lo is None or x >= lo.value) and (hi is None or x <= hi.value)]
        frac = len(inside) / len(nums)
        if sheet.value and parse_value(sheet.value) is not None and parse_value(sheet.value).unit == "%":
            ok = matches(parse_value(sheet.value), frac * 100)
        elif sheet.quantifier in QUANT_TEST:
            ok = QUANT_TEST[sheet.quantifier](frac)
        else:
            return _undecided("share without a quantifier or a percentage")
        return Outcome(ok, round(frac, 4), f"{len(inside)} of {len(nums)} in range")

    if t == "ratio":
        nums = sorted({float(c) for c in cells if _is_num(c)}, reverse=True)
        stated = parse_value(sheet.value or "")
        if stated is None or not nums:
            return _undecided("ratio without a readable figure")
        ref = sheet.reference or "value"
        num = nums[0]
        if ref == "second_max":
            if len(nums) < 2:
                return _undecided("no second value")
            den = nums[1]
        elif ref == "median":
            den = statistics.median([float(c) for c in cells if _is_num(c)])
        elif ref == "mean":
            den = statistics.mean([float(c) for c in cells if _is_num(c)])
        elif ref == "min":
            den = nums[-1]
        else:
            rv = parse_value(sheet.reference_value or "")
            if rv is None:
                return _undecided("ratio reference value unreadable")
            den = rv.value
        if not den:
            return _undecided("zero denominator")
        true = round(num / den, 3)
        loose = Value(stated.raw, stated.value, stated.decimals, stated.unit, True)
        return Outcome(matches(loose, true, loose=stated.approximate), true, f"{num} / {den}")

    if t == "universal":
        v = parse_value(sheet.value or "")
        if v is None or sheet.op is None:
            return _undecided("universal without an operator and a figure")
        cmp = {"<": lambda a: a < v.value, "<=": lambda a: a <= v.value, ">": lambda a: a > v.value,
               ">=": lambda a: a >= v.value, "=": lambda a: a == v.value, "!=": lambda a: a != v.value}[sheet.op]
        nums = [float(c) for c in cells if _is_num(c)]
        if not nums:
            return _undecided("no numeric cell")
        n_ok = sum(1 for x in nums if cmp(x))
        ok = n_ok == len(nums) if (sheet.quantifier or "all") != "none" else n_ok == 0
        return Outcome(ok, n_ok, f"{n_ok} of {len(nums)} satisfy {sheet.op} {v.value}")

    if t == "trend":
        nums = [float(c) for c in cells if _is_num(c)]
        if len(nums) < 8 or sheet.direction not in ("up", "down", "flat"):
            return _undecided("trend needs a direction and at least 8 points")
        q = max(2, len(nums) // 4)
        a, b = statistics.mean(nums[:q]), statistics.mean(nums[-q:])
        change = (b - a) / abs(a) if a else 0.0
        true = "up" if change > 0.05 else "down" if change < -0.05 else "flat"
        return Outcome(true == sheet.direction, true, f"mean of first vs last quarter: {change:+.1%}")

    return _undecided(f"type {t!r} is not verifiable")
