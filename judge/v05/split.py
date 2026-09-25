"""Step 1 — cut an answer into claims and table rows (code only).

A claim is a sentence carrying a digit or a trigger word (triggers.txt). Table lines are
taken apart from the prose: they are checked cell by cell against the result
(tables.py), not translated. Every discarded sentence is kept, so the rate of discarded
text is measurable (PROTOCOL_v0.5_JUDGE.md: "discarded sentences are logged").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TRIGGERS_FILE = Path(__file__).with_name("triggers.txt")


def load_triggers() -> list[str]:
    words = []
    for line in TRIGGERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line.lower())
    return sorted(set(words), key=len, reverse=True)


# prefix match at a word start: broad on purpose ("accelerat" -> accelerating)
TRIGGER_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in load_triggers()) + r")", re.I)


@dataclass
class Claim:
    idx: int
    text: str          # the sentence, markdown emphasis removed
    context: str       # the sentence before it (pronouns, "the table above"...)
    trigger: str       # "digit" or the trigger word that selected it


@dataclass
class Split:
    claims: list[Claim]
    table_lines: list[tuple[str | None, str]]   # (section heading, raw line)
    discarded: list[str]


def _clean(s: str) -> str:
    s = re.sub(r"[*_`]+", "", s)
    s = re.sub(r"^\s*(?:[-•>]|\d+[.)])\s+", "", s)
    s = re.sub(r"^#+\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _sentences(block: str) -> list[str]:
    # split after . ! ? when followed by a space and an upper-case letter, a digit or an
    # opening mark; never inside a number (29,943.44) or an abbreviation like "e.g."
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(“\"'*])", block)
    return [p for p in (x.strip() for x in parts) if p]


def is_table_line(line: str) -> bool:
    s = line.strip()
    if s.startswith("|") and s.count("|") >= 2:
        return True
    return False


def split_answer(answer: str) -> Split:
    claims: list[Claim] = []
    tables: list[tuple[str | None, str]] = []
    discarded: list[str] = []
    heading: str | None = None
    in_code = False
    prev = ""
    for line in answer.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if not s:
            continue
        if in_code or is_table_line(s):
            tables.append((heading, s))
            continue
        if re.match(r"^(#+\s+|\*\*[^*]+\*\*\s*$)", s):
            heading = _clean(s)
        for sent in _sentences(s):
            text = _clean(sent)
            if not text:
                continue
            if re.search(r"\d", text):
                trig = "digit"
            else:
                m = TRIGGER_RE.search(text)
                trig = m.group(1).lower() if m else ""
            if trig:
                claims.append(Claim(len(claims), text, prev, trig))
            else:
                discarded.append(text)
            prev = text
    return Split(claims, tables, discarded)
