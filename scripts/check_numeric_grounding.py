"""
Numeric grounding check — find fabricated figures without asking a judge.

For every model answer, extracts the figures it states and classifies each one
against the database:

    window        the value appears in the first N rows the model was given
    population    it appears in the full result but NOT in the window, i.e. the
                  model stated something it could not see
    derived_local it equals a difference, sum, ratio or percentage change of two
                  anchored figures written NEXT TO IT in the same sentence — the
                  model showed its work ("~35,700 in November (241,937 -> 277,636)")
    shared        several models produced the same figure independently on the
                  same question: a derivation this tool does not model, not an
                  invention
    nowhere       none of the above -> candidate fabrication

An answer that every judge scored highly while containing "nowhere" figures is a
candidate common error: exactly the case inter-judge agreement can never surface,
because agreement is not correctness.

Scope, stated up front:

  * Only figures that carry fabrication risk are checked: decimals, and integers
    of four digits or more. Small integers ("5 entries") are too ambiguous to
    check mechanically and would drown the signal in false flags. Zero-padded
    tokens are identifier fragments (BK23-0067 -> "0067") and bare four-digit
    integers in the calendar range are period references; both are skipped.
  * The local-derivation and cross-model filters remove false positives at the
    cost of possibly hiding a fabricated figure that matches a nearby arithmetic
    combination. They filter OUT, so they can only make this tool more
    conservative.
  * WHAT THIS TOOL CANNOT DO, measured on the held-out suite 2026-08-04. It
    narrows 105 answers to 18 flagged cases (9 with every judge above the band),
    which is a usable review list. It does NOT produce a clean automatic count:
    the survivors are still dominated by legitimate derivations written in forms
    the tool does not model. Three checked by hand, three different causes:
      "1,307"  = 683 + 357 + 267, a three-term sum; only pairs are tested
      "15,000" = 45,000 - 29,943, but the first operand sits far earlier in the
                 text, outside LOCAL_WINDOW
      "17.3"   is written "17.3 k", i.e. 17,300; unit suffixes are not parsed
    The tail of ways a model can legitimately write a derived figure is long.
    Treat the output as a REVIEW LIST for a human, never as a count.
  * This finds NUMERIC fabrication only. It cannot see a scope error ("ends at X"
    vs "at the end of the period shown, X") nor a false claim about a
    distribution — nemotron/ledger-l10-02, "the majority sit between 5,000 and
    10,000" against a true median of 3,079.46, is missed by this checker exactly
    as it was missed by all four judges. What comes out is a FLOOR on the
    common-error rate, never the rate.

Usage:
    python scripts/check_numeric_grounding.py
    python scripts/check_numeric_grounding.py --show nemotron-3-nano-30b/ledger-l9-01
"""
from __future__ import annotations

import argparse
import collections
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
REL_TOL = 0.005        # 0.5 % — covers rounding and cent-level drift
MIN_INT_DIGITS = 4
LOCAL_WINDOW = 250     # characters either side, where a model shows its work
MAX_LOCAL_OPERANDS = 12

SPACES = "    "
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
NUM_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[" + SPACES + r",]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![\w])"
)


def parse_number(tok: str) -> float | None:
    """Locale-tolerant. '29 943,44' and '29,943.44' are the same value.

    The French decimal comma has already cost this project a x1000 error, so the
    separator is decided by position, never assumed.
    """
    t = re.sub(r"[" + SPACES + r"]", "", tok)
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    try:
        return float(t)
    except ValueError:
        return None


def worth_checking(tok: str, val: float) -> bool:
    clean = re.sub(r"[" + SPACES + r",]", "", tok)
    has_decimal = ("." in tok) or ("," in tok and len(tok.rpartition(",")[2]) != 3)
    if len(clean) > 1 and clean[0] == "0" and not clean.startswith("0."):
        return False
    if not has_decimal and len(clean) == 4 and 1900 <= val <= 2100:
        return False
    return True if has_decimal else len(clean) >= MIN_INT_DIGITS


def extract_numbers(text: str) -> list[tuple[str, float, int]]:
    """(token, value, position). Position feeds the local-derivation check."""
    masked = DATE_RE.sub(lambda m: " " * len(m.group(0)), text)
    out = []
    for m in NUM_RE.finditer(masked):
        tok = m.group(1)
        val = parse_number(tok)
        if val is not None and worth_checking(tok, val):
            out.append((tok, val, m.start()))
    return out


def numeric_cells(rows) -> set[float]:
    return {
        float(v)
        for r in rows
        for v in r
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def aggregates(rows, ncols: int) -> set[float]:
    out: set[float] = {float(len(rows))}
    for i in range(ncols):
        nums = [r[i] for r in rows if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)]
        if not nums:
            continue
        out |= {float(min(nums)), float(max(nums)), float(sum(nums)), float(len(nums))}
        out.add(sum(nums) / len(nums))
    return out


def close(a: float, b: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1e-9)
    if abs(a - b) / scale <= REL_TOL:
        return True
    return any(round(a, nd) == round(b, nd) for nd in (0, 1, 2))


def close_to(val: float, pool: set[float]) -> bool:
    return any(close(val, p) for p in pool)


def derivable_locally(val: float, pos: int, all_nums, anchored: set[float]) -> bool:
    """Did the model show its work next to the figure?

    Collects the anchored figures written within LOCAL_WINDOW characters and asks
    whether `val` is their difference, sum, ratio or percentage change.
    """
    operands = [
        v for _, v, p in all_nums
        if abs(p - pos) <= LOCAL_WINDOW and v != val and close_to(v, anchored)
    ]
    operands = sorted(operands, key=lambda v: -abs(v))[:MAX_LOCAL_OPERANDS]
    for i, a in enumerate(operands):
        for b in operands[i + 1:]:
            if close(val, abs(a - b)) or close(val, a + b):
                return True
            lo, hi = (b, a) if abs(a) > abs(b) else (a, b)
            if lo and (close(val, hi / lo) or close(val, (hi - lo) / abs(lo) * 100)):
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="data/questions-heldout.jsonl")
    ap.add_argument("--judges", default="grok43-v03,gemini25pro-v03,deepseek4pro-v03")
    ap.add_argument("--band", type=int, default=80,
                    help="judge score at or above which a flag becomes a common-error candidate")
    ap.add_argument("--show", default=None, help="model/question to detail")
    args = ap.parse_args()

    questions = {
        json.loads(l)["id"]: json.loads(l)
        for l in (ROOT / args.dataset).read_text(encoding="utf-8").splitlines()
        if l.strip()
    }

    pools: dict[str, dict] = {}
    for qid, q in questions.items():
        db = next(k for k in DB_FILES if k in q.get("database", "").lower())
        con = sqlite3.connect(DB_FILES[db])
        cur = con.execute(q["gold_sql"].strip().rstrip(";"))
        ncols = len(cur.description)
        rows = cur.fetchall()
        con.close()
        win = rows[:CAP]
        pools[qid] = {
            "window": numeric_cells(win) | aggregates(win, ncols),
            "population": numeric_cells(rows) | aggregates(rows, ncols),
        }

    judges = args.judges.split(",")

    # ---- pass 1: classify every figure, defer the "nowhere" verdict ---------
    records = []
    for path in sorted((ROOT / "runs").glob("*-heldout.jsonl")):
        if "scored" in path.name:
            continue
        model = path.name.replace("-heldout.jsonl", "")
        scores = {}
        for j in judges:
            p = ROOT / "runs" / f"{model}-heldout.scored-{j}.jsonl"
            if p.exists():
                scores[j] = {
                    json.loads(l)["id"]: json.loads(l)
                    for l in p.read_text(encoding="utf-8").splitlines() if l.strip()
                }
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d["id"] not in pools:
                continue
            pool = pools[d["id"]]
            anchored = pool["window"] | pool["population"]
            nums = extract_numbers(d["model_answer"])
            counts = collections.Counter()
            unresolved = []
            for tok, val, pos in nums:
                if close_to(val, pool["window"]):
                    counts["window"] += 1
                elif close_to(val, pool["population"]):
                    counts["population"] += 1
                elif derivable_locally(val, pos, nums, anchored):
                    counts["derived_local"] += 1
                else:
                    unresolved.append((tok, round(val, 4)))
            F = [scores[j][d["id"]]["faithfulness"] for j in judges if d["id"] in scores.get(j, {})]
            records.append({
                "model": model, "id": d["id"], "counts": counts,
                "unresolved": unresolved, "F": F, "min_F": min(F) if F else None,
            })

    # ---- pass 2: a figure several models produced independently is a derivation
    seen = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in records:
        for _, val in r["unresolved"]:
            seen[r["id"]][val].add(r["model"])
    for r in records:
        solo = [(t, v) for t, v in r["unresolved"] if len(seen[r["id"]][v]) == 1]
        r["counts"]["shared"] = len(r["unresolved"]) - len(solo)
        r["counts"]["nowhere"] = len(solo)
        r["nowhere_tokens"] = [t for t, _ in solo]

    total = collections.Counter()
    for r in records:
        total.update(r["counts"])
    flagged = [r for r in records if r["counts"]["nowhere"] > 0]
    candidates = [r for r in flagged if r["min_F"] is not None and r["min_F"] >= args.band]

    print(f"cas analyses : {len(records)}")
    print("figures classees : " + "  ".join(
        f"{k}={total[k]}" for k in ("window", "population", "derived_local", "shared", "nowhere")))
    print()
    print(f"cas avec >=1 figure non ancree       : {len(flagged)}")
    print(f"  ... et tous les juges a F>={args.band}  : {len(candidates)}  <-- a verifier a la main")
    print()
    for r in sorted(candidates, key=lambda x: -x["counts"]["nowhere"]):
        print(f"  {r['model'][:24]:26} {r['id']:16} nowhere={r['counts']['nowhere']:2}  "
              f"F={r['F']}  {r['nowhere_tokens'][:6]}")

    if args.show:
        m, q = args.show.split("/")
        for r in records:
            if r["model"] == m and r["id"] == q:
                print(f"\n=== {m} / {q} ===")
                print("  " + "  ".join(f"{k}={r['counts'][k]}" for k in
                      ("window", "population", "derived_local", "shared", "nowhere")))
                print(f"  non ancrees : {r['nowhere_tokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
