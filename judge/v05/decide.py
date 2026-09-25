"""Step 4 — fixed rules from claims to a verdict (code only). PROTOCOL_v0.5_JUDGE.md.

Scope is decided by code first:
  1. an explicit window marker in the sentence ("shown", "displayed", "table above"...)
     -> rows_shown;
  2. an explicit population marker ("in the ledger", "entire", "whole", "overall"...)
     -> all_data;
  3. otherwise, if the answer made a SPECIFIC declaration of what it received and that
     declaration is true (rule r3 of the scope law: a date range or row count matching
     the rows shown), silent sentences inherit rows_shown;
  4. otherwise the translator's scope.

Verdicts:
  condemned  - at least one claim proved false (material if it bears on what the question
               asks, minor otherwise);
  acquitted  - no false claim, every claim bearing on the question verified true, and at
               least one such claim;
  undecided  - everything else. Never counted as faithful.
"""
from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from resolve_scope import DATE_TOKEN, ROWS_EXCLUDE, ROWS_RE, norm_date, same_date  # noqa: E402

from .result import Result
from .verify import evaluate

WINDOW_MARK = re.compile(
    r"\b(shown|displayed|visible|returned|provided|the rows I have|table above|result above|"
    r"output above|period shown|first \d+ rows|\d+ rows? (?:shown|displayed|returned|provided)|"
    r"capped|truncated|in (?:these|the) \d+ (?:rows|entries|movements|lines|days|records))\b", re.I)
POP_MARK = re.compile(
    r"\b(in the (?:entire |whole |full )?(?:ledger|dataset|data|database|table)|entire|whole|overall|"
    r"across the (?:full|whole|entire) (?:period|ledger|dataset)|of all time|ever)\b", re.I)
# the scope law's r3 declaration, with the arrow real answers use ("2023-01-01 → 2024-01-09")
RANGE_RE = re.compile(rf"({DATE_TOKEN})\s*(?:to|through|until|–|—|-|→|->|\bthru\b)\s*({DATE_TOKEN})", re.I)

BANDS = {"acquitted": ("faithful", "100", 100),
         "material": ("unfaithful_material", "<=40", 20),
         "minor": ("unfaithful_minor", "41-99", 70),
         "undecided": ("undecided", "", None)}


def declaration(answer: str, res: Result) -> dict | None:
    """A true, specific declaration of the rows received, or None."""
    if not res.shown:
        return None
    lo, hi = str(res.shown[0][0]), str(res.shown[-1][0])
    for m in RANGE_RE.finditer(answer):
        d1, d2 = norm_date(m.group(1)), norm_date(m.group(2))
        if d1 and d2 and same_date(d1, lo) and same_date(d2, hi):
            return {"kind": "date range", "quote": m.group(0)}
    excluded = [(m.start(), m.end()) for m in ROWS_EXCLUDE.finditer(answer)]
    for m in ROWS_RE.finditer(answer):
        if any(a <= m.start() < b for a, b in excluded):
            continue
        n = int(next(g for g in m.groups() if g))
        if n == len(res.shown):
            return {"kind": "row count", "quote": m.group(0)}
    return None


@dataclass
class ClaimResult:
    sentence: str
    sheet: dict
    scope: str
    scope_source: str
    holds: bool | None
    true_value: object = None
    detail: str = ""
    other_scope_holds: bool | None = None


@dataclass
class Verdict:
    verdict: str
    band: str
    faithfulness: int | None
    reason: str
    claims: list[ClaimResult] = field(default_factory=list)
    table: dict = field(default_factory=dict)
    declaration: dict | None = None


def decide_scope(sentence: str, sheet, decl) -> tuple[str, str]:
    if sheet.scope == "interpretation":
        return "interpretation", "translator"
    win, pop = WINDOW_MARK.search(sentence), POP_MARK.search(sentence)
    if win and not pop:
        return "rows_shown", f"marker '{win.group(0)}'"
    if pop and not win:
        return "all_data", f"marker '{pop.group(0)}'"
    if decl and not pop:
        return "rows_shown", f"inherits the declaration '{decl['quote']}'"
    return sheet.scope, "translator"


def judge_claims(pairs, res: Result, decl) -> list[ClaimResult]:
    out = []
    for sentence, sheet in pairs:
        if sheet.rejected:
            out.append(ClaimResult(sentence, asdict(sheet), sheet.scope, "rejected", None,
                                   detail=sheet.rejected))
            continue
        scope, source = decide_scope(sentence, sheet, decl)
        if scope == "interpretation":
            out.append(ClaimResult(sentence, asdict(sheet), scope, source, None, detail="not a data claim"))
            continue
        o = evaluate(sheet, res, scope)
        other = None
        if o.holds is False and scope == "all_data" and res.truncated:
            other = evaluate(sheet, res, "rows_shown").holds    # a window fact stated as the data?
        out.append(ClaimResult(sentence, asdict(sheet), scope, source, o.holds, o.true_value,
                               o.detail, other))
    return out


def verdict_for(claims: list[ClaimResult], table) -> Verdict:
    data_claims = [c for c in claims if c.scope != "interpretation"]
    false = [c for c in data_claims if c.holds is False]
    table_false = bool(table.mismatches)
    if false or table_false:
        material = table_false or any(c.sheet.get("answers_question") for c in false)
        key = "material" if material else "minor"
        v, b, f = BANDS[key]
        why = "; ".join(f"{c.sheet.get('type')} '{c.sheet.get('span')}' ({c.scope}): true {c.true_value!r}"
                        for c in false)
        if table_false:
            why = (why + "; " if why else "") + f"{len(table.mismatches)} table cell(s) contradict the result"
        return Verdict(v, b, f, why)
    on_question = [c for c in data_claims if c.sheet.get("answers_question")]
    undecided_q = [c for c in on_question if c.holds is None]
    verified_q = [c for c in on_question if c.holds is True]
    if (on_question and not undecided_q and verified_q) or (not on_question and table.cells_checked and not undecided_q):
        v, b, f = BANDS["acquitted"]
        return Verdict(v, b, f, f"{len(verified_q)} claim(s) on the question verified, "
                                f"{table.cells_checked} table cell(s) checked")
    v, b, f = BANDS["undecided"]
    reasons = [c.detail for c in undecided_q][:3] or ["no claim bearing on the question could be verified"]
    return Verdict(v, b, f, "undecided: " + "; ".join(reasons))
