"""Step 2's output format: the fact sheet, its JSON schema, and its validation (code).

A sheet is a translation, never a judgement. It is accepted only if its span and its
stated value really occur in the sentence it claims to translate: a translator that
invents text gets its sheet rejected, and the claim becomes undecided.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TYPES = ["total", "count", "extreme", "end_value", "point", "share", "ratio", "universal", "trend", "other"]
SCOPES = ["rows_shown", "all_data", "interpretation"]
QUANTIFIERS = ["all", "almost_all", "most", "majority", "half", "few", "none"]

SHEET_PROPS = {
    "span": {"type": "string"},
    "scope": {"type": "string", "enum": SCOPES},
    "type": {"type": "string", "enum": TYPES},
    "column": {"type": ["string", "null"]},
    "value": {"type": ["string", "null"]},
    "which": {"type": ["string", "null"], "enum": ["max", "min", "first", "last", None]},
    "at": {"type": ["string", "null"]},
    "low": {"type": ["string", "null"]},
    "high": {"type": ["string", "null"]},
    "quantifier": {"type": ["string", "null"], "enum": QUANTIFIERS + [None]},
    "op": {"type": ["string", "null"], "enum": ["<", "<=", ">", ">=", "=", "!=", None]},
    "filter_column": {"type": ["string", "null"]},
    "filter_op": {"type": ["string", "null"], "enum": ["eq", "startswith", "contains", None]},
    "filter_value": {"type": ["string", "null"]},
    "reference": {"type": ["string", "null"],
                  "enum": ["second_max", "median", "mean", "min", "value", None]},
    "reference_value": {"type": ["string", "null"]},
    "direction": {"type": ["string", "null"], "enum": ["up", "down", "flat", None]},
    "answers_question": {"type": "boolean"},
}
REQUIRED = ["span", "scope", "type", "column", "value", "answers_question"]


def schema_for(columns: list[str]) -> dict:
    """The translator's output schema for one result: `column` can only be one of the
    result's real columns (or "none"), so a sheet can never name a column that is not
    there. `value` is always present ("" when the sentence states no figure)."""
    props = dict(SHEET_PROPS)
    props["column"] = {"type": "string", "enum": list(columns) + ["none"]}
    props["value"] = {"type": "string"}
    return {
        "type": "object",
        "properties": {"claims": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "properties": props, "required": REQUIRED}}},
        "required": ["claims"],
    }


SCHEMA = schema_for([])


@dataclass
class Sheet:
    span: str
    scope: str
    type: str
    answers_question: bool
    column: str | None = None
    value: str | None = None
    which: str | None = None
    at: str | None = None
    low: str | None = None
    high: str | None = None
    quantifier: str | None = None
    op: str | None = None
    filter_column: str | None = None
    filter_op: str | None = None
    filter_value: str | None = None
    reference: str | None = None
    reference_value: str | None = None
    direction: str | None = None
    rejected: str | None = None           # why the code refused this sheet
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Sheet":
        known = {k: d.get(k) for k in SHEET_PROPS}
        known["answers_question"] = bool(known.get("answers_question"))
        known["span"] = known.get("span") or ""
        known["scope"] = known.get("scope") or "all_data"
        known["type"] = known.get("type") or "other"
        if known.get("column") in ("none", ""):
            known["column"] = None
        if known.get("value") == "":
            known["value"] = None
        return cls(**known)


def _norm(s: str) -> str:
    from .numbers import words_to_digits
    s = re.sub(r"[*_`$€£]+", "", s or "")
    for ch in "    ":
        s = s.replace(ch, " ")
    s = s.replace("‑", "-").replace("−", "-")
    s = words_to_digits(s)
    return re.sub(r"\s+", " ", s).strip().lower()


WORD_VALUES = {"up", "down", "flat", "all", "none", "most", "majority", "few", "half", "initial"}


MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]


def _figures_supported(v: str, sentence: str) -> bool:
    """Every figure of the sheet's value is a figure of the sentence (compared as values:
    '20,000 to 53,000' is supported by 'between 20,000 and 53,000')."""
    from .numbers import find_values, words_to_digits
    mine = [x.value for x in find_values(words_to_digits(v))]
    theirs = {round(x.value, 6) for x in find_values(words_to_digits(sentence))}
    return bool(mine) and all(round(x, 6) in theirs or round(-x, 6) in theirs for x in mine)


def _date_supported(at: str, sentence: str, context: str) -> bool:
    """A normalised date ('2024-01') is supported if its year (and day) are in the sentence
    and its month is named in the sentence or the one before ('each January ... in 2024')."""
    from .numbers import date_parts
    parts = date_parts(at)
    if not parts:
        return False
    both = f"{context} {sentence}".lower()
    for y, m, d in parts:
        if y is not None and not re.search(rf"\b{y}\b", sentence):
            return False
        if m is not None and not (re.search(rf"\b({MONTH_NAMES[m - 1]}|{MONTH_NAMES[m - 1][:3]})\b", both)
                                  or re.search(rf"\b\d{{4}}-{m:02d}\b", sentence)):
            return False
        if d is not None and not re.search(rf"\b0?{d}\b", sentence):
            return False
    return True


def validate(sheet: Sheet, sentence: str, context: str = "") -> Sheet:
    """Reject a sheet whose span or stated figures are not in the sentence."""
    sent = _norm(sentence)
    if not sheet.span or _norm(sheet.span) not in sent:
        sheet.rejected = "span not found verbatim in the sentence"
        return sheet
    for name in ("value", "at", "low", "high", "reference_value"):
        v = getattr(sheet, name)
        if not v:
            continue
        if name == "value" and not re.search(r"\d", _norm(v)) and v.lower() in WORD_VALUES:
            setattr(sheet, name, None)            # a direction/quantifier word, not a figure
            continue
        core = re.sub(r"^\s*(?:[<>=~≈]+|more than|less than|over|under|above|below|about|approximately)\s*",
                      "", _norm(v))
        if core in sent:
            continue
        if name == "at" and _date_supported(v, sentence, context):
            continue
        if name != "at" and re.search(r"\d", core) and _figures_supported(v, sentence):
            continue
        sheet.rejected = f"{name} {v!r} not found in the sentence"
        return sheet
    if sheet.scope == "interpretation" and re.search(r"\d", sheet.span):
        # a figure is never an opinion: an 'interpretation' carrying one would escape checking
        sheet.rejected = "interpretation scope on a span that carries a figure"
    return sheet
