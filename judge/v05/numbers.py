"""Numbers and dates as a model writes them, read back as values (GBAG v0.5 judge).

Everything here is deterministic. The judge never condemns on a number it could not read,
so the parser prefers returning None to guessing.

Formats met in real answers: 29,943.44 · 29 943,44 · 45,000 · 476 k · ≈ 476 k € · 7x ·
−15.6% · +83.1 % · 0.01 · 2023-01-01 · 9 January 2024 · January 9, 2024 · 2023-01.
The French decimal comma has already cost this project a x1000 error: the separator is
decided by position, never assumed (same rule as scripts/check_numeric_grounding.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SPACES = "     "
MINUS = "−–‒"          # unicode minus and dashes used as a sign
APPROX = re.compile(r"(~|≈|\babout\b|\baround\b|\broughly\b|\bapproximately\b|\bapprox\.?|"
                    r"\bnearly\b|\balmost\b|\bsome\b|\bover\b|\bmore than\b|\bless than\b|"
                    r"\bunder\b|\bclose to\b|\bjust\b)", re.I)

NUM_TOKEN = re.compile(
    r"(?<![\w.])([+" + MINUS + r"-]?)"
    r"(\d{1,3}(?:[" + SPACES + r",]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s?(k|K|m|M|bn|%|x|×)?(?![\w])"
)

MONTHS = ("january february march april may june july august september october "
          "november december").split()
MON3 = [m[:3] for m in MONTHS]
_MON = "|".join(MONTHS + MON3)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(\d{{4}})\b", re.I), "dmy"),
    (re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), "mdy"),
    (re.compile(r"\b(\d{4})-(\d{2})\b(?!-\d)"), "ym"),
    (re.compile(rf"\b({_MON})\.?,?\s+(\d{{4}})\b", re.I), "my"),
]


@dataclass(frozen=True)
class Value:
    raw: str
    value: float
    decimals: int          # decimals as written: sets the tolerance of an exact figure
    unit: str | None       # "%", "x", or None
    approximate: bool      # an approximation marker precedes it, or a k/M suffix


def _to_float(body: str) -> tuple[float, int] | None:
    t = re.sub("[" + SPACES + "]", "", body)
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    try:
        v = float(t)
    except ValueError:
        return None
    decimals = len(t.split(".")[1]) if "." in t else 0
    return v, decimals


WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
                "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100}
_WORD_RATIO = re.compile(r"\b(twice|double|triple|half|(" + "|".join(WORD_NUMBERS) + r")\s*(?:times|-fold|fold|x))\b", re.I)
_WORD_NUM = re.compile(r"\b(" + "|".join(WORD_NUMBERS) + r")\b", re.I)


def words_to_digits(text: str) -> str:
    """'twice' -> '2x', 'eight times' -> '8x', 'six' -> '6' — so a figure written in words
    is read like a figure written in digits. Used on both the sentence and the sheet."""
    def ratio(m):
        w = m.group(1).lower()
        if w == "twice" or w == "double":
            return "2x"
        if w == "triple":
            return "3x"
        if w == "half":
            return "0.5x"
        return f"{WORD_NUMBERS[m.group(2).lower()]}x"
    text = _WORD_RATIO.sub(ratio, str(text))
    return _WORD_NUM.sub(lambda m: str(WORD_NUMBERS[m.group(1).lower()]), text)


def parse_value(text: str) -> Value | None:
    """The first number in `text`, with its unit and precision. None if none is readable.
    Figures written in words ("twice", "eight times", "six") are read too."""
    vals = find_values(text)
    if not vals:
        vals = find_values(words_to_digits(text))
    return vals[0] if vals else None


def find_values(text: str) -> list[Value]:
    # "-$18,489.48", "−€ 5,000": the currency sign sits between the sign and the digits
    text = re.sub(r"([+\-" + MINUS + r"])\s*[$€£]\s*", r"\1", str(text))
    text = re.sub(r"[$€£]\s*(?=\d)", "", text)
    masked = mask_dates(text)
    out = []
    for m in NUM_TOKEN.finditer(masked):
        sign, body, suffix = m.group(1), m.group(2), m.group(3)
        parsed = _to_float(body)
        if parsed is None:
            continue
        v, dec = parsed
        if sign and (sign in MINUS or sign == "-"):
            v = -v
        unit = None
        approx = bool(APPROX.search(masked[max(0, m.start() - 16):m.start()]))
        if suffix in ("k", "K"):
            v, approx, dec = v * 1e3, True, 0
        elif suffix in ("m", "M"):
            v, approx, dec = v * 1e6, True, 0
        elif suffix == "bn":
            v, approx, dec = v * 1e9, True, 0
        elif suffix == "%":
            unit = "%"
        elif suffix in ("x", "×"):
            unit = "x"
        out.append(Value(text[m.start():m.end()], v, dec, unit, approx))
    return out


def mask_dates(text: str) -> str:
    """Blank out dates so that 2023-01-01 is not read as the numbers 2023, 1 and 1."""
    for rx, _ in DATE_PATTERNS:
        text = rx.sub(lambda m: " " * len(m.group(0)), text)
    return text


def find_dates(text: str) -> list[str]:
    """ISO strings: yyyy-mm-dd, or yyyy-mm for a month."""
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            try:
                if kind == "ymd":
                    out.append(f"{g[0]}-{g[1]}-{g[2]}")
                elif kind == "dmy":
                    out.append(f"{g[2]}-{_mon(g[1]):02d}-{int(g[0]):02d}")
                elif kind == "mdy":
                    out.append(f"{g[2]}-{_mon(g[0]):02d}-{int(g[1]):02d}")
                elif kind == "ym":
                    out.append(f"{g[0]}-{g[1]}")
                elif kind == "my":
                    out.append(f"{g[1]}-{_mon(g[0]):02d}")
            except ValueError:
                continue
    return out


def parse_date(text: str) -> str | None:
    d = find_dates(str(text))
    return d[0] if d else None


_PART_DM = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\b\.?|\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
_PART_M = re.compile(rf"\b({_MON})\b\.?", re.I)


def date_parts(text: str) -> list[tuple[str | None, int | None, int | None]]:
    """Every (year, month, day) a text names, even partially: "26 Nov" -> (None, 11, 26);
    "mid-May, late July" -> (None, 5, None), (None, 7, None). Full dates keep their year.
    The verb "may" is not a month: only a capitalised "May" counts on its own."""
    text = str(text)
    out: list[tuple[str | None, int | None, int | None]] = []
    for d in find_dates(text):
        y, m, *rest = d.split("-")
        out.append((y, int(m), int(rest[0]) if rest else None))
    if out:
        return out
    for m in _PART_DM.finditer(text):
        if m.group(1):
            out.append((None, _mon(m.group(2)), int(m.group(1))))
        else:
            out.append((None, _mon(m.group(3)), int(m.group(4))))
    if out:
        return out
    for m in _PART_M.finditer(text):
        if m.group(1).lower() == "may" and m.group(1) != "May":
            continue
        out.append((None, _mon(m.group(1)), None))
    return out


def parts_match(stated: str, cell) -> bool:
    """A (possibly partial) stated date against a result cell: every component the
    statement gives must agree. With several candidates ("late July, early August"), one
    agreeing is enough."""
    cd = find_dates(str(cell))
    if not cd:
        return False
    cy, cm, *cr = cd[0].split("-")
    cday = int(cr[0]) if cr else None
    for y, m, d in date_parts(stated):
        if y is not None and y != cy:
            continue
        if m is not None and m != int(cm):
            continue
        if d is not None and cday is not None and d != cday:
            continue
        return True
    return False


def _mon(name: str) -> int:
    n = name.lower().rstrip(".")[:3]
    if n not in MON3:
        raise ValueError(name)
    return MON3.index(n) + 1


def matches(stated: Value, true: float, *, loose: bool = False) -> bool:
    """Does the stated figure describe the true value?

    Exact figures get the tolerance of their written precision (half a unit of the last
    decimal, plus 0.5 % for rounding drift). Approximate figures get 10 %, and `loose`
    (ratios said "roughly") 25 %. The judge condemns only a clear difference: when in
    doubt about precision, it tolerates.
    """
    if true is None:
        return False
    t = float(true)
    if stated.unit == "%" and abs(t) <= 1.0 and abs(stated.value) > 1.0:
        t *= 100.0                          # a share stored as 0.x, said as x %
    if loose:
        rel = 0.25
    elif stated.approximate:
        rel = 0.10
    else:
        rel = 0.005
    half_unit = 0.5 * 10 ** (-stated.decimals) if not stated.approximate else 0
    diff = abs(stated.value - t)
    return diff <= half_unit + 1e-9 or diff <= rel * max(abs(t), 1e-9)
