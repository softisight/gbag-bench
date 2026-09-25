"""Step 3 — compute the true value of a fact sheet at a scope (code only).

`evaluate(sheet, result, scope)` returns an Outcome: True / False / None (undecided) with
the true value it computed. None is returned whenever the sheet cannot be evaluated on
the result — unknown column, unreadable figure, type `other` — never a guess.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .numbers import Value, date_parts, find_dates, matches, parse_value, parts_match
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


SINGULAR_SUPERLATIVE = re.compile(
    r"\b(the|its|a|an)\s+(single\s+)?(highest|lowest|largest|smallest|biggest|maximum|minimum|"
    r"peak|low point|high point|top|record|strongest|weakest|deepest|tightest)\b|"
    r"\b(all-time|record)\s+(high|low)\b|\bhighest point\b|\blowest point\b", re.I)


def _cell_matches(stated: str, cell) -> bool:
    """A stated label/date/number against one result cell."""
    if cell is None or stated is None:
        return False
    if find_dates(str(cell)) and date_parts(stated):
        return parts_match(stated, cell)
    if _is_num(cell):
        v = parse_value(stated)
        return v is not None and matches(v, float(cell))
    norm = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
    return norm(stated) == norm(cell) and norm(stated) != ""


ABOVE = re.compile(r"\b(above|over|more than|exceed(?:s|ed|ing)?|greater than|at least|beyond|>)\s*[~≈]?\s*$", re.I)
BELOW = re.compile(r"\b(below|under|less than|at most|no more than|<)\s*[~≈]?\s*$", re.I)


def comparator(sheet) -> str | None:
    """'>' when the words just before the stated figure say "above 30,000", '<' for
    "below", None for a plain value. Read in the sentence, not asked of the model."""
    text = (sheet.extra.get("sentence") or sheet.span or "")
    v = (sheet.value or "").strip()
    if not v:
        return None
    for probe in (v, re.sub(r"^\s*[<>=~≈]+\s*", "", v)):
        i = text.find(probe)
        if i > 0:
            before = text[max(0, i - 24):i]
            if ABOVE.search(before):
                return ">"
            if BELOW.search(before):
                return "<"
    if re.match(r"^\s*(>|more than|over|above)", v, re.I):
        return ">"
    if re.match(r"^\s*(<|less than|under|below)", v, re.I):
        return "<"
    return None


def _value_matches(stated: str, true, cmp: str | None = None) -> bool | None:
    if true is None:
        return None
    if not _is_num(true):
        return _cell_matches(stated, true)
    v = parse_value(stated)
    if v is None:
        return None
    if cmp == ">":
        return float(true) >= v.value or matches(v, float(true))
    if cmp == "<":
        return float(true) <= v.value or matches(v, float(true))
    return matches(v, float(true))


END_FIRST = re.compile(r"\b(open(?:ed|ing|s)?|start(?:ed|ing|s)?|began|begins|first|initial|from)\b", re.I)
END_LAST = re.compile(r"\b(end(?:ed|ing|s)?|clos(?:e|ed|ing|es)|final(?:ly)?|last|latest|to|by|stands at|settl(?:ed|ing))\b", re.I)


STRONG_END = re.compile(r"\b(end(?:s|ed|ing)?\s+(?:at|on|with)|clos(?:es|ed|ing)|final|last|"
                        r"open(?:s|ed|ing)?\s+(?:at|with)|start(?:s|ed)?\s+at|finish(?:es|ed)?)\b", re.I)


def _infer_end(sheet) -> str | None:
    """first/last from the words of the span, when the translator left `which` empty."""
    span = sheet.span or ""
    f, l = END_FIRST.search(span), END_LAST.search(span)
    if f and not l:
        return "first"
    if l and not f:
        return "last"
    return None


def _infer_direction(span: str) -> str | None:
    """up/down/flat from the words, when the translator left `direction` empty."""
    up = re.search(r"\b(increas\w*|ris(?:e|es|ing)|rose|grow\w*|grew|upward|climb\w*|positive trend|gain\w*)\b", span, re.I)
    down = re.search(r"\b(decreas\w*|declin\w*|fall\w*|fell|drop\w*|downward|negative trend|shrink\w*)\b", span, re.I)
    flat = re.search(r"\b(stable|flat|steady|unchanged|constant)\b", span, re.I)
    found = [d for d, m in (("up", up), ("down", down), ("flat", flat)) if m]
    return found[0] if len(found) == 1 else None


def _infer_reference(span: str) -> str | None:
    """The denominator of a ratio, from the words ("eight times the median")."""
    if re.search(r"\bmedian\b", span, re.I):
        return "median"
    if re.search(r"\b(average|mean)\b", span, re.I):
        return "mean"
    if re.search(r"\b(next[- ]largest|second[- ]largest|any other|next biggest)\b", span, re.I):
        return "second_max"
    return None


def _point(sheet, res: Result, rows, ci) -> bool:
    """Is the stated figure the column's value on a row the statement locates?"""
    if not sheet.value or not sheet.at:
        return False
    for r in rows:
        if any(_cell_matches(sheet.at, cell) for cell in r) and _value_matches(sheet.value, r[ci]):
            return True
    return False


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
        fi = res.col(sheet.filter_column) if sheet.filter_column else None
        if sheet.filter_column and fi is not None:
            fv = (sheet.filter_value or "").lower()
            op = sheet.filter_op or "eq"
            test = {"eq": lambda c: str(c).lower() == fv,
                    "startswith": lambda c: str(c).lower().startswith(fv),
                    "contains": lambda c: fv in str(c).lower()}[op]
            sel = [r for r in rows if test(r[fi])]
            if not sel:
                # a filter that selects nothing says more about the translation than about
                # the answer ("payroll" against codes like "PY"): never grounds for condemning
                return _undecided(f"filter {sheet.filter_column} {op} {fv!r} selects no row")
        stated = parse_value(sheet.value or "")
        if stated is None:
            return _undecided("count without a readable figure")
        # An aggregated result already holds the count in a cell ("BK: 683 entries" is the
        # nb_entries cell of row BK; a one-row result is the count itself): counting the
        # result's rows would be counting the wrong thing.
        cells = [float(c) for r in sel for c in r if _is_num(c)]
        if len(sel) <= 1 or (fi is not None and len(sel) == 1):
            if cells:
                return Outcome(any(matches(stated, c) for c in cells), cells,
                               "count read from the aggregated row")
        if sheet.filter_column and fi is None:
            return _undecided(f"filter column {sheet.filter_column!r} not in the result")
        n = len(sel)
        if matches(stated, n):
            return Outcome(True, n, f"{n} matching rows")
        if not sheet.filter_column:
            # an unfiltered count that misses the row count may be a lookup whose filter the
            # translation dropped ("OB - Opening balances: 1 entry" on a per-journal result):
            # true if a row named in the sentence carries it, undecided if some row does
            said = (sheet.extra.get("sentence") or "") + " " + (sheet.span or "")
            norm = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
            words = {norm(w) for w in re.findall(r"[\w-]+", said)}
            for r in rows:
                if any(norm(c) in words for c in r if isinstance(c, str) and norm(c)) and \
                        any(matches(stated, float(c)) for c in r if _is_num(c)):
                    return Outcome(True, stated.value, "count read from the row the sentence names")
            if any(matches(stated, float(c)) for r in rows for c in r if _is_num(c)):
                return _undecided("unfiltered count: the figure is a cell of the result, not the row count")
        return Outcome(False, n, f"{n} matching rows")

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

    if t == "end_value" and sheet.at and not STRONG_END.search(sheet.span or ""):
        # "from ~35,000 on 2023-04-25": a value at a date that is not where the data starts
        # or ends is a point, not an end — unless the words say end ("ends at", "closes").
        end_rows = [rows[0], rows[-1]]
        if not any(_cell_matches(sheet.at, cell) for r in end_rows for cell in r):
            sheet.type = "point"
            return evaluate(sheet, res, scope)

    if t in ("extreme", "end_value"):
        if not sheet.value and not sheet.at:
            return _undecided(f"{t} states neither a value nor where")
        which = sheet.which
        if t == "end_value" and which not in ("first", "last"):
            which = _infer_end(sheet)
        if t == "extreme" and which not in ("max", "min"):
            words = sheet.span or ""
            up = re.search(r"\b(highest|largest|biggest|maximum|max|peak|top|strongest|record high)\b", words, re.I)
            down = re.search(r"\b(lowest|smallest|minimum|min|trough|bottom|tightest|weakest|record low)\b", words, re.I)
            which = "max" if up and not down else "min" if down and not up else None
        if t == "extreme":
            if which not in ("max", "min"):
                return _undecided("extreme without max/min")
            keyed = [(c, r) for c, r in zip(cells, rows) if c is not None]
            best = (max if which == "max" else min)(keyed, key=lambda cr: _sortable(cr[0]))[0]
            hit_rows = [r for c, r in keyed if c == best]
        else:
            if which not in ("first", "last"):
                return _undecided("end_value without first/last")
            r = rows[0] if which == "first" else rows[-1]
            best, hit_rows = r[ci], [r]
        ok = True
        if sheet.value:
            ok = _value_matches(sheet.value, best, comparator(sheet))
        if ok and sheet.at:
            ok = any(_cell_matches(sheet.at, cell) for r in hit_rows for cell in r)
        if ok is False and t == "extreme":
            # Only a SINGULAR superlative ("the highest point", "the peak") asserts the global
            # extreme. "peaks of 52,900 and 50,423" names local points: if the figure is really
            # there at the stated place it is a true fact about a row, otherwise undecided —
            # never condemned as a false maximum.
            said = (sheet.extra.get("sentence") or "") + " " + (sheet.span or "")
            if not SINGULAR_SUPERLATIVE.search(said):
                point = _point(sheet, res, rows, ci)
                return Outcome(True if point else None, best,
                               "local point found at the stated place" if point
                               else "not the global extreme, and not asserted as one")
        return Outcome(ok, best, f"{which} = {best!r}")

    if t == "point":
        # "net movement of +18,528.56 in May 2024": the column's value on the row(s) the
        # statement locates. The place comes from `at`, or from the dates in the span.
        if not sheet.value:
            return _undecided("point without a value")
        locator = sheet.at or " ".join(find_dates(sheet.span or "")) or sheet.span
        located = [r for r in rows if any(_cell_matches(locator, cell) for cell in r)]
        if not located:
            return _undecided("the stated place matches no row")
        cmp = comparator(sheet)
        hits = [r[ci] for r in located if _value_matches(sheet.value, r[ci], cmp)]
        if hits:
            return Outcome(True, hits[0], f"found on {len(located)} located row(s)")
        if any(_value_matches(sheet.value, c, cmp) for r in located for c in r if _is_num(c)):
            # the figure IS on the located row, under another column: the translation picked
            # the wrong column (a credit read as a debit). That is not a proof of falsity.
            return _undecided("the figure is on the located row under another column")
        if len(located) <= 3:
            return Outcome(False, [r[ci] for r in located], f"value differs on the {len(located)} located row(s)")
        return _undecided(f"{len(located)} rows located, none matches — place too vague to condemn")

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
        if ref == "value" and not sheet.reference_value:
            ref = _infer_reference(sheet.span or "") or ref
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
        if sheet.direction not in ("up", "down", "flat"):
            sheet.direction = _infer_direction(sheet.span or "")
        if len(nums) < 8 or sheet.direction not in ("up", "down", "flat"):
            return _undecided("trend needs a direction and at least 8 points")
        # A direction has several honest readings. Each one below is a standard measure;
        # the claim is TRUE only if they all agree with it, FALSE only if none does, and
        # undecided when they disagree among themselves (no single reading is a proof).
        def label(change):
            return "up" if change > 0.05 else "down" if change < -0.05 else "flat"
        q = max(2, len(nums) // 4)
        a, b = statistics.mean(nums[:q]), statistics.mean(nums[-q:])
        readings = {"quarter means": label((b - a) / abs(a) if a else 0.0),
                    "first vs last": label((nums[-1] - nums[0]) / abs(nums[0]) if nums[0] else 0.0)}
        if any(x < 0 for x in nums) and any(x > 0 for x in nums):
            # a flow column (net movements): its direction over the period is its sum's sign
            total = sum(nums)
            readings["sum of flows"] = label(total / (sum(abs(x) for x in nums) or 1))
        found = set(readings.values())
        detail = ", ".join(f"{k}: {v}" for k, v in readings.items())
        if found == {sheet.direction}:
            return Outcome(True, sheet.direction, detail)
        if sheet.direction not in found:
            return Outcome(False, sorted(found), detail)
        return _undecided(f"readings disagree ({detail})")

    return _undecided(f"type {t!r} is not verifiable")
