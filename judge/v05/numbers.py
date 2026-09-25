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

SPACES = "    "
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


def parse_value(text: str) -> Value | None:
    """The first number in `text`, with its unit and precision. None if none is readable."""
    vals = find_values(text)
    return vals[0] if vals else None


def find_values(text: str) -> list[Value]:
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
            except ValueError:
                continue
    return out


def parse_date(text: str) -> str | None:
    d = find_dates(str(text))
    return d[0] if d else None


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
