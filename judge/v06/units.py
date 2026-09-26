"""Step 2 — every figure and every date of a selected sentence is one unit (code only).

Two figures in one sentence are two units, never one (v0.5.0 test-01). A date is a unit
too: "last = 2023-07-19" states a value (the data's last date). When a date only locates
another figure, Jev scores it `place` and it is not judged.

Not units (masked by code before any figure is read):
  * bare years used as labels ("in 2024"); month-day fragments ("05-16");
  * document numbers (BK23-0067, OB-2023, VAT-2024-Q4), account codes ("account 512",
    "account (512)"), class labels ("class 7"), quarter labels (Q4);
  * method parameters ("1.5×IQR");
  * small integers (<= 12) that are list numbers or ranks ("1.", "Top 10") — kept only when
    a count noun follows ("12 entries", "nine VAT entries").

A figure written as a labelled field whose label names a result column ("Total Amount:
19264.82") gets its column and its family (`cell`) from CODE: nobody is asked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from judge.v05.numbers import DATE_PATTERNS, Value, date_parts, find_dates, find_values, words_to_digits

HYPHENS = str.maketrans({"‐": "-", "‑": "-"})
MASKS = [
    re.compile(r"\b[A-Z]{1,4}\d{2}-\d{3,4}\b"),                          # BK23-0067, SI24-9001
    re.compile(r"\b[A-Z]{2,4}-\d{4}(?:-Q\d)?(?:-\d{2})?\b"),             # OB-2023, VAT-2024-Q4
    re.compile(r"\baccounts?\s*\(?\s*\d{2,6}\s*\)?(?:\s*(?:,|and|/)\s*\d{2,6})*", re.I),  # account (512)
    re.compile(r"\bclass(?:es)?\s+\d+\b", re.I),                          # class 7
    re.compile(r"\d+(?:\.\d+)?\s*[×x]\s*IQR\b", re.I),                    # 1.5×IQR
    re.compile(r"\bQ[1-4]\b"),
    re.compile(r"(?<![\d-])\d{2}-\d{2}(?![\d-])"),                        # 05-16 (month-day)
    # rank selectors, not counts: "the top three journals", "Top 10 entries", "first five"
    re.compile(r"\b(?:top|first|last|bottom|leading)\s+(?:\d{1,2}|one|two|three|four|five|six|seven|"
               r"eight|nine|ten|eleven|twelve|fifteen|twenty)\b", re.I),
]
COUNT_NOUN = re.compile(r"^\s*(?:\w+\s+){0,2}?(entries|entry|rows?|lines?|days?|items?|journals?|months?|"
                        r"transactions?|movements?|postings?|records?|accounts?|customers?|suppliers?|"
                        r"invoices?|payments?|categories|weeks?)\b", re.I)


@dataclass
class Unit:
    idx: int
    raw: str
    figure: Value | None        # a number
    date: str | None            # or an ISO date / month
    sentence: str
    context: str
    places: list[str]           # every date/period named in the sentence
    forced_column: str | None = None   # set by code for a labelled field


def _masked(text: str) -> str:
    for rx in MASKS:
        text = rx.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _is_year_label(v: Value) -> bool:
    return (v.unit is None and v.decimals == 0 and 1900 <= v.value <= 2100
            and "," not in v.raw and " " not in v.raw.strip())


def _is_list_number(v: Value, text: str) -> bool:
    if v.unit or v.decimals or v.value > 12 or v.value < 0 or "," in v.raw:
        return False
    i = text.find(v.raw)
    after = text[i + len(v.raw):] if i >= 0 else ""
    return not COUNT_NOUN.match(after)


def _field_column(sentence: str, raw: str, columns: list[str]) -> str | None:
    """'Total Amount: 19264.82' -> 'total_amount' when the label names a result column."""
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    i = sentence.find(raw)
    if i < 0:
        return None
    m = re.search(r"([A-Za-z][A-Za-z _]{1,40}?)\s*[*_]*\s*[:=]\s*[*_$€£\s]*$", sentence[:i])
    if not m:
        return None
    label = norm(m.group(1))
    return next((c for c in columns if norm(c) == label), None)


def units_of(sentence: str, context: str, start: int, columns: list[str] | None = None) -> list[Unit]:
    sentence = sentence.translate(HYPHENS)
    places = find_dates(sentence)
    if not places and date_parts(sentence):
        # partial places ("mid-May, late July, and early August"): the sentence itself is the
        # locator, read component by component by parts_match
        places = [sentence]
    out: list[Unit] = []
    for rx, _ in DATE_PATTERNS:
        for m in rx.finditer(sentence):
            d = find_dates(m.group(0))
            if d:
                out.append(Unit(0, m.group(0), None, d[0], sentence, context, places))
    text = _masked(sentence)
    # "one" is an article far more often than a figure ("this one posting"): never converted
    protected = words_to_digits(re.sub(r"(?i)\bone\b", "o_n_e", text))
    for v in find_values(protected):
        if _is_year_label(v) or _is_list_number(v, protected):
            continue
        u = Unit(0, v.raw, v, None, sentence, context, places)
        if columns:
            u.forced_column = _field_column(sentence, v.raw, columns)
        out.append(u)
    for i, u in enumerate(out):
        u.idx = start + i
    return out
