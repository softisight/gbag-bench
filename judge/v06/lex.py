"""The v0.6-lex fallback: the fact family from a fixed lexicon, no model at all.

The keyword NEAREST to the figure decides (within the same clause, 8 words either side);
without one, the family is `cell`. PROTOCOL_v0.6_JUDGE.md said "first match in the
sentence"; nearest-to-the-figure is deviation V1, fixed before any measurement, because a
sentence like "starts at 45,000 ... and ends at 29,943.44" carries two families.
"""
from __future__ import annotations

import re

LEXICON = [
    ("sum", r"total|turnover|sum|overall revenue|in all|combined"),
    ("maximum", r"highest|largest|maximum|max|peak|biggest|top|record high|strongest"),
    ("minimum", r"lowest|smallest|minimum|min|trough|bottom|record low|tightest"),
    ("last", r"ends?|ending|ended|closes|closing|closed|final|last|latest"),
    ("first", r"starts?|started|starting|opening|opened|opens|first|initial"),
    ("ratio", r"times|\d+x|fold|twice|double|triple"),
    ("share", r"%|percent|share|majority|proportion|of the"),
    ("count", r"entries|rows|lines|items|days|postings|transactions|movements|records|journals"),
    ("change", r"change|increase[sd]?|decrease[sd]?|drop(?:ped|s)?|rise|rose|fell|fall|grew|growth|decline[sd]?"),
]
_TOKEN = re.compile(r"\S+")


def family_of(unit) -> str:
    s = unit.sentence
    i = s.find(unit.raw)
    if i < 0:
        return "cell"
    clause_start = max(s.rfind(ch, 0, i) for ch in ",;:(") + 1
    ends = [s.find(ch, i + len(unit.raw)) for ch in ",;:)"]
    clause_end = min([e for e in ends if e >= 0] or [len(s)])
    before = _TOKEN.findall(s[clause_start:i])[-8:]
    after = _TOKEN.findall(s[i + len(unit.raw):clause_end])[:8]
    best = None
    for side, dist, tok in [("before", len(before) - k, t) for k, t in enumerate(before)] + \
                           [("after", k + 1, t) for k, t in enumerate(after)]:
        for fam, rx in LEXICON:
            # a count keyword only counts right after the figure ("12 entries"), never
            # "the largest recurring items at ~6,045"
            if fam == "count" and not (side == "after" and dist == 1):
                continue
            if re.fullmatch(rf"(?i)\W*(?:{rx})\W*", tok) and (best is None or dist < best[0]):
                best = (dist, fam)
    if unit.figure is not None and unit.figure.unit == "%" and (best is None or best[1] not in ("share", "change")):
        return "change" if re.search(r"(?i)change|increase|decrease|drop|rise|fell|grew|decline|vs|versus", s) else "share"
    if unit.figure is not None and unit.figure.unit == "x":
        return "ratio"
    return best[1] if best else "cell"
