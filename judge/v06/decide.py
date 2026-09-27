"""Steps 5 and 7 — scope by code first, then the verdict (PROTOCOL_v0.6_JUDGE.md).

A mismatch is a condemnation only when it is a PROOF:
  * the family is accepted (Jev >= 0.80 with a 0.10 lead, or the lexicon in lex mode);
  * the scope is decided (marker, true declaration, accepted Jev score), or the figure
    matches at neither scope;
  * the figure matches the family's facts in NO numeric column (if the chosen column
    misses but another column matches, the translation is doubted: undecided);
  * for `cell`, the rows the sentence locates exist and the figure is absent from them.
Everything else is undecided, never guessed.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from resolve_scope import DATE_TOKEN, ROWS_EXCLUDE, ROWS_RE, norm_date, same_date  # noqa: E402

from judge.v05.decide import POP_MARK, ROWS_RE_V05, WINDOW_MARK
from judge.v05.result import Result

from .facts import check, located_rows

RANGE_RE = re.compile(rf"({DATE_TOKEN})\s*(?:to|through|until|–|—|-|→|->|\bthru\b)\s*({DATE_TOKEN})", re.I)
FRAME = re.compile(r"\b(shown|displayed|output|result|returned|covers|covered|received|capped|truncated|"
                   r"visible|provided|available)\b", re.I)


def declaration(answer: str, res: Result) -> dict | None:
    """A true declaration of what was received. A date range counts only inside a sentence
    carrying a frame word: "first = 2023-01-01 to last = 2023-07-19" is a claim, not one."""
    if not res.shown:
        return None
    lo, hi = str(res.shown[0][0]), str(res.shown[-1][0])
    for sent in re.split(r"(?<=[.!?\n])\s+", answer):
        if not FRAME.search(sent):
            continue
        for m in RANGE_RE.finditer(sent):
            d1, d2 = norm_date(m.group(1)), norm_date(m.group(2))
            if d1 and d2 and same_date(d1, lo) and same_date(d2, hi):
                return {"kind": "date range", "quote": m.group(0)}
    excluded = [(m.start(), m.end()) for m in ROWS_EXCLUDE.finditer(answer)]
    for rx in (ROWS_RE, ROWS_RE_V05):
        for m in rx.finditer(answer):
            if any(a <= m.start() < b for a, b in excluded):
                continue
            n = int(next(g for g in m.groups() if g))
            if n == len(res.shown):
                return {"kind": "row count", "quote": m.group(0)}
    return None


POP_MARK_V06 = re.compile(r"\b(of the (?:entire |whole |full )?(?:ledger|dataset|data set|database)|the ledger's|"
                          r"in the (?:entire |whole |full )?(?:ledger|dataset|data set|data|database))\b", re.I)
POP_STRICT = re.compile(r"\b(entire|whole (?:ledger|dataset|data set|period|year|history)|"
                        r"across the (?:full|whole|entire) (?:period|ledger|dataset)|of all time)\b", re.I)
# Coverage beats size (truth-set case 4): "the table above (200 rows) lists EVERY
# transaction" asserts the whole data, whatever the size descriptor says.
COVERAGE = re.compile(r"\b(every|all(?: of)?(?: the)?) (?:\w+ ){0,2}(transactions?|postings?|entries|movements|"
                      r"lines|rows|records|days|journal entries)\b|\bthe (?:full|complete|entire) "
                      r"(?:ledger|list|history|set|record)\b", re.I)


def scope_of(sentence: str, jev_scope: str | None, decl) -> tuple[str | None, str]:
    cov = COVERAGE.search(sentence)
    if cov and not re.search(r"\b(shown|displayed|visible)\b", cov.group(0), re.I):
        return "all_data", f"coverage '{cov.group(0)}'"
    win = WINDOW_MARK.search(sentence)
    # v0.5's list included "overall", which answers use as a bullet label ("Overall trend:");
    # v0.6 keeps only explicit population markers
    pop = POP_STRICT.search(sentence) or POP_MARK_V06.search(sentence)
    if win and not pop:
        return "rows_shown", f"marker '{win.group(0)}'"
    if pop and not win:
        return "all_data", f"marker '{pop.group(0)}'"
    if decl and not pop:
        return "rows_shown", f"declaration '{decl['quote']}'"
    if jev_scope:
        return jev_scope, "jev"
    return None, "uncertain"


@dataclass
class UnitResult:
    unit: str
    sentence: str
    family: str | None
    family_source: str
    column: str | None
    scope: str | None
    scope_source: str
    holds: bool | None
    true_values: list = field(default_factory=list)
    detail: str = ""
    on_question: bool = True
    scores: dict = field(default_factory=dict)


def judge_unit(unit, res: Result, family: str | None, family_src: str, column: str | None,
               reference: str | None, scope: str | None, scope_src: str, on_q: bool, scores: dict) -> UnitResult:
    R = lambda holds, tv, detail: UnitResult(unit.raw, unit.sentence, family, family_src, column, scope,
                                             scope_src, holds, tv, detail, on_q, scores)
    if family == "place" or (unit.date and family not in ("first", "last", "cell", None)):
        # a date next to "the peak" says when; it locates, it is not judged
        return UnitResult(unit.raw, unit.sentence, "place", family_src, column, scope, scope_src,
                          None, [], "a place, not a claim", on_q, scores)
    if unit.figure is not None and unit.places and not AGGREGATE_WORDS.search(unit.sentence):
        # "from 3,644.12 in January 2023 to 475,982.19 by July 2024": the sentence names the
        # place, and the figure is that row's value in the FULL result -> a true point fact.
        # Words that claim an aggregate or an end ("ends at", "total", "the highest") still
        # require the aggregate (v0.5 lesson: an end value at a date is a point unless the
        # words say end).
        from .facts import _fig_matches, _num
        for r in located_rows(unit, res, "all_data"):
            if any(_num(c) and _fig_matches(unit, float(c)) for c in r):
                return R(True, [next(float(c) for c in r if _num(c) and _fig_matches(unit, float(c)))],
                         "the value of the row the sentence names (full result)")
    ci = res.col(column) if column else None
    cols = [ci] if ci is not None else None

    def at(sc):
        st, tv, d = check(family, unit, res, sc, cols, reference)
        if st == "mismatch" and cols is not None:
            st2, tv2, d2 = check(family, unit, res, sc, None, reference)
            if st2 == "match":
                return "doubt", tv2, "the figure fits another column: translation doubted"
        return st, tv, d

    if family is None:
        # family uncertain: supported if some family fits at a decided scope; never condemned
        for fam in ("cell", "sum", "maximum", "minimum", "last", "first", "ratio", "count", "change", "share"):
            st, tv, _ = check(fam, unit, res, scope or "all_data", None, None)
            if st == "match":
                return R(True, tv, f"family uncertain; fits '{fam}'")
        return R(None, [], "family uncertain and no fact fits")

    def refutable() -> str | None:
        """Why a mismatch cannot be a proof here, or None if it can."""
        if family in SUBSET_SENSITIVE and _subset_named(unit.sentence, res):
            return "the sentence names a subset; the whole column cannot refute it"
        if family in ("maximum", "minimum") and not SINGULAR_SUPERLATIVE.search(unit.sentence):
            return "no singular superlative: not asserted as the column's extreme"
        return None

    if scope is not None:
        st, tv, d = at(scope)
        if st == "match":
            return R(True, tv, d)
        if st == "mismatch" and refutable():
            return R(None, tv, refutable())
        if st == "mismatch":
            if family == "cell":
                loc = located_rows(unit, res, scope)
                if not (0 < len(loc) <= 3):
                    return R(None, tv, "cell: the sentence locates no row precisely enough to condemn")
            other = at("rows_shown")[0] if scope == "all_data" and res.truncated else None
            why = "true only on the rows shown, stated about the data" if other == "match" else d
            return R(False, tv, why)
        return R(None, tv, d)

    # scope uncertain: true on the full result -> true; neither -> false; shown only -> undecided
    st_full, tv_full, d_full = at("all_data")
    if st_full == "match":
        return R(True, tv_full, "true on the full result (scope uncertain)")
    st_shown, tv_shown, _ = at("rows_shown")
    if st_shown == "match":
        return R(None, tv_full, "true only on the rows shown, scope uncertain")
    if st_full == "mismatch" and st_shown == "mismatch":
        if refutable():
            return R(None, tv_full, refutable())
        if family == "cell" and not (0 < len(located_rows(unit, res, "all_data")) <= 3):
            return R(None, tv_full, "cell: no precise row to condemn")
        return R(False, tv_full, "false at both scopes")
    return R(None, tv_full, d_full)


# Words that make a figure at a named date claim an END or an EXTREME, not that row's value.
# "total" / "all" next to a date describe the row ("the cumulative total ... by July 2024 is
# X" is the running total on that date), so they are not in the list.
AGGREGATE_WORDS = re.compile(r"\b(ends?|ending|ended|clos(?:es|ed|ing)|final|"
                             r"highest|lowest|largest|smallest|maximum|minimum|peak|record|absolute)\b", re.I)
SUBSET_SENSITIVE = {"sum", "maximum", "minimum", "first", "last", "share", "change", "ratio"}
SINGULAR_SUPERLATIVE = re.compile(
    r"\b(the|its|a|an)\s+(single\s+)?(highest|lowest|largest|smallest|biggest|maximum|minimum|"
    r"peak|low point|high point|top|record|strongest|weakest|deepest|tightest)\b|"
    r"\b(all-time|record)\s+(high|low)\b|\bhighest point\b|\blowest point\b|\babsolute (minimum|maximum)\b", re.I)


def _subset_named(sentence: str, res: Result) -> bool:
    """Does the sentence name a subset of the rows — a short text value of the result
    (a journal code, a document number, a category) used as a qualifier?"""
    values = set()
    for r in res.full:
        for c in r:
            if isinstance(c, str) and 1 < len(c) <= 12 and not c[:4].isdigit():   # not a date
                values.add(c)
    return any(re.search(rf"(?<![\w-]){re.escape(v)}(?![\w-])", sentence) for v in values)


BANDS = {"acquitted": ("faithful", "100", 100), "material": ("unfaithful_material", "<=40", 20),
         "minor": ("unfaithful_minor", "41-99", 70), "undecided": ("undecided", "", None)}


STRONG_UNJUDGED = re.compile(r"\b(every|each) year\b|\b(progressively|consistently|always|never|"
                             r"without exception|in all (years|months))\b", re.I)


def verdict(units: list[UnitResult], table, unjudged: list[str] | None = None) -> dict:
    """`unjudged`: selected sentences that carry no figure. v0.6 does not judge them; one
    that makes a STRONG claim ("progressively higher each year", "always", "never")
    forbids an acquittal — the answer can only be condemned (on another figure) or
    undecided, never passed on a claim nobody checked."""
    false = [u for u in units if u.holds is False]
    if false or table.mismatches:
        key = "material" if table.mismatches or any(u.on_question for u in false) else "minor"
        v, b, f = BANDS[key]
        why = "; ".join(f"{u.family} {u.unit!r} ({u.scope or 'both scopes'}): true {u.true_values[:2]} — {u.detail}"
                        for u in false)
        if table.mismatches:
            why = (why + "; " if why else "") + f"{len(table.mismatches)} table cell(s) contradict the result"
        return {"verdict": v, "band": b, "faithfulness": f, "reason": why}
    judged = [u for u in units if u.family != "place" and u.on_question]
    undecided = [u for u in judged if u.holds is None]
    verified = [u for u in judged if u.holds is True]
    strong = [s for s in (unjudged or []) if STRONG_UNJUDGED.search(s)]
    if strong and not undecided:
        v, b, f = BANDS["undecided"]
        return {"verdict": v, "band": b, "faithfulness": f,
                "reason": f"undecided: a strong claim without a figure is not checked by v0.6: '{strong[0][:120]}'"}
    if (verified or table.cells_checked) and not undecided:
        v, b, f = BANDS["acquitted"]
        return {"verdict": v, "band": b, "faithfulness": f,
                "reason": f"{len(verified)} figure(s) on the question verified, {table.cells_checked} table cell(s)"}
    v, b, f = BANDS["undecided"]
    reasons = [f"{u.unit!r}: {u.detail}" for u in undecided][:3] or ["no figure on the question could be verified"]
    return {"verdict": v, "band": b, "faithfulness": f, "reason": "undecided: " + "; ".join(reasons)}
