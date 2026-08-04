"""
Numeric grounding check — find fabricated figures without asking a judge.

For every model answer, extracts the figures it states and classifies each one
against the database:

    window      the value appears in the first N rows the model was given
    population  it appears in the full result but NOT in the window, i.e. the
                model stated something it could not see
    derived     it equals an aggregate of the window or the population
                (count / sum / avg / min / max on any column)
    nowhere     none of the above -> candidate fabrication

An answer that a judge scored highly while containing "nowhere" figures is a
candidate common error: exactly the case that inter-judge agreement can never
surface, because agreement is not correctness.

Scope, stated up front:

  * Only figures that carry fabrication risk are checked: decimals, and integers
    of four digits or more. Small integers ("5 entries", "3 accounts") are too
    ambiguous to check mechanically and would drown the signal in false flags.
  * Dates are excluded, they are matched as text elsewhere.
  * KNOWN GAP, measured 2026-08-04: the derivation pool holds per-column
    aggregates but NOT differences between two visible values, which is the most
    common operation in a BI answer. claude-fable-5 on ledger-l9-03 was flagged
    for "~35,700 in November (241,937 -> 277,636)" - a correct subtraction of two
    values it could see. Cross-model convergence filters most of this out (a
    figure produced by several models independently is derived, not invented),
    taking 86 flagged cases down to 8, but the survivors still need the
    sentence-local subtraction check before the flag list is usable as-is.
  * This finds NUMERIC fabrication only. It cannot see a scope error
    ("ends at X" vs "at the end of the period shown, X") nor a false claim about
    a distribution ("the majority sit between 5,000 and 10,000" - both figures
    are real, the falsehood is in "the majority"). The checker and the judges
    therefore share part of their blind spot: what comes out is a FLOOR on the
    common-error rate, not the rate.

Usage:
    python scripts/check_numeric_grounding.py
    python scripts/check_numeric_grounding.py --show nemotron-3-nano-30b/ledger-l9-01
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DB_FILES = {
    "sakila": ROOT / "databases" / "sakila.sqlite",
    "chinook": ROOT / "databases" / "chinook.sqlite",
    "northwind": ROOT / "databases" / "northwind.sqlite",
    "ledger": ROOT / "databases" / "ledger.sqlite",
}
CAP = 200
REL_TOL = 0.005          # 0.5 % — covers rounding and unit-of-cent drift
MIN_INT_DIGITS = 4       # below this, integers are too ambiguous to check

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
# 1 234,56 | 1,234.56 | 1234.56 | 45000 | 45 000
NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:[  , ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![\w])")


def parse_number(tok: str) -> float | None:
    """Locale-tolerant. '29 943,44' and '29,943.44' are the same value.

    The French decimal comma has already cost this project a x1000 error, so the
    separator is decided by position, never assumed.
    """
    t = tok.replace(" ", " ").replace(" ", "").replace(" ", "")
    if "," in t and "." in t:
        # whichever comes last is the decimal separator
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    try:
        return float(t)
    except ValueError:
        return None


def worth_checking(tok: str, val: float) -> bool:
    clean = re.sub(r"[\s,  ]", "", tok)
    has_decimal = ("." in tok) or ("," in tok and len(tok.rpartition(",")[2]) != 3)
    # A zero-padded token is an identifier fragment, not a value: document numbers
    # such as BK23-0067 split into "0067". No real amount is written that way.
    if len(clean) > 1 and clean[0] == "0" and not clean.startswith("0."):
        return False
    # Bare four-digit integers in the calendar range are period references
    # ("in 2024", "since 2023"), not figures claimed from the data.
    if not has_decimal and len(clean) == 4 and 1900 <= val <= 2100:
        return False
    if has_decimal:
        return True
    return len(clean) >= MIN_INT_DIGITS


def extract_numbers(text: str) -> list[tuple[str, float]]:
    text = DATE_RE.sub(" ", text)
    out = []
    for m in NUM_RE.finditer(text):
        tok = m.group(1)
        val = parse_number(tok)
        if val is not None and worth_checking(tok, val):
            out.append((tok, val))
    return out


def numeric_cells(rows, cols) -> set[float]:
    vals = set()
    for r in rows:
        for v in r:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.add(float(v))
    return vals


def aggregates(rows, cols) -> set[float]:
    """Every aggregate a model could legitimately have computed."""
    out: set[float] = {float(len(rows))}
    for i in range(len(cols)):
        nums = [r[i] for r in rows if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)]
        if not nums:
            continue
        out |= {float(min(nums)), float(max(nums)), float(sum(nums)), float(len(nums))}
        out.add(sum(nums) / len(nums))
    return out


def close_to(val: float, pool: set[float]) -> bool:
    for p in pool:
        if val == p:
            return True
        scale = max(abs(val), abs(p), 1e-9)
        if abs(val - p) / scale <= REL_TOL:
            return True
    # the model may have rounded, or dropped the cents
    for nd in (0, 1, 2):
        r = round(val, nd)
        for p in pool:
            if round(p, nd) == r:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="data/questions-heldout.jsonl")
    ap.add_argument("--judges", default="grok43-v03,gemini25pro-v03,deepseek4pro-v03")
    ap.add_argument("--show", default=None, help="model/question to detail")
    args = ap.parse_args()

    questions = {
        json.loads(l)["id"]: json.loads(l)
        for l in (ROOT / args.dataset).read_text(encoding="utf-8").splitlines()
        if l.strip()
    }

    # per question: the value pools, computed once
    pools: dict[str, dict] = {}
    for qid, q in questions.items():
        db = next((k for k in DB_FILES if k in q.get("database", "").lower()), None)
        con = sqlite3.connect(DB_FILES[db])
        cur = con.execute(q["gold_sql"].strip().rstrip(";"))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        con.close()
        win = rows[:CAP]
        pools[qid] = {
            "window": numeric_cells(win, cols) | aggregates(win, cols),
            "population": numeric_cells(rows, cols) | aggregates(rows, cols),
        }

    judges = args.judges.split(",")
    runs = sorted((ROOT / "runs").glob("*-heldout.jsonl"))
    rows_out = []
    for path in runs:
        if "scored" in path.name:
            continue
        model = path.name.replace("-heldout.jsonl", "")
        scores = {}
        for j in judges:
            p = ROOT / "runs" / f"{model}-heldout.scored-{j}.jsonl"
            if p.exists():
                scores[j] = {json.loads(l)["id"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d["id"] not in pools:
                continue
            pool = pools[d["id"]]
            nowhere = []
            counts = {"window": 0, "population": 0, "nowhere": 0}
            for tok, val in extract_numbers(d["model_answer"]):
                if close_to(val, pool["window"]):
                    counts["window"] += 1
                elif close_to(val, pool["population"]):
                    counts["population"] += 1
                else:
                    counts["nowhere"] += 1
                    nowhere.append(tok)
            F = [scores[j][d["id"]]["faithfulness"] for j in judges if d["id"] in scores.get(j, {})]
            rows_out.append({
                "model": model, "id": d["id"], **counts,
                "nowhere_tokens": nowhere, "F": F,
                "min_F": min(F) if F else None,
            })

    flagged = [r for r in rows_out if r["nowhere"] > 0]
    unanimous_high = [r for r in flagged if r["min_F"] is not None and r["min_F"] >= 80]

    cited_unseen = [r for r in rows_out if r["population"] > 0 and (r["min_F"] or 0) >= 80]
    print(f"cas analyses                           : {len(rows_out)}")
    print(f"cas contenant >=1 chiffre 'nulle part'  : {len(flagged)}")
    print(f"  ... dont TOUS les juges donnent F>=80 : {len(unanimous_high)}  <-- candidats erreur commune")
    print(f"cas citant un chiffre hors fenetre, tous juges F>=80 : {len(cited_unseen)}")
    print()
    print("=== candidats erreur commune, tries par nombre de chiffres non ancres ===")
    for r in sorted(unanimous_high, key=lambda x: -x["nowhere"])[:25]:
        print(f"  {r['model'][:24]:26} {r['id']:16} nulle_part={r['nowhere']:3}  F={r['F']}  ex: {r['nowhere_tokens'][:4]}")

    if args.show:
        m, q = args.show.split("/")
        for r in rows_out:
            if r["model"] == m and r["id"] == q:
                print(f"\n=== {m} / {q} ===")
                print(f"  fenetre={r['window']}  population_seule={r['population']}  nulle_part={r['nowhere']}")
                print(f"  jetons non ancres : {r['nowhere_tokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
