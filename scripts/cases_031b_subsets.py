"""Build the two subsets of the judge experiment "031-B" from runs/031b/cases.jsonl.

  * cases-gt200.jsonl       : the answers whose result has more than 200 rows (the rows the
                              answering model could not all see);
  * cases-gt200-short.jsonl : 12 of them, for a judge too slow for the whole set. The two
                              answers already judged when the set was cut are kept; five
                              faithful and five unfaithful answers are drawn from the others
                              (seed 7, answers sorted by id). The draw reads no verdict.

Usage (repo root):  python scripts/cases_031b_subsets.py [--check]
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "runs" / "031b"
ROW_CAP = 200
SEED, PER_TRUTH = 7, 5
ALREADY_JUDGED = ["nemotron-3-nano-30b__ledger-l10-01", "nemotron-3-nano-30b__ledger-l10-02"]


def rows_of(case: dict) -> int:
    with sqlite3.connect(f"file:{(ROOT / 'databases' / (case['database'] + '.sqlite')).as_posix()}?mode=ro",
                         uri=True) as cx:
        return len(cx.execute(case["gold_sql"]).fetchall())


def large(cases: list[dict]) -> list[dict]:
    return [c for c in cases if rows_of(c) > ROW_CAP]


def short(cases: list[dict]) -> list[dict]:
    kept = [c for c in cases if c["id"] in ALREADY_JUDGED]
    rest = sorted((c for c in cases if c["id"] not in ALREADY_JUDGED), key=lambda c: c["id"])
    rng = random.Random(SEED)
    for truth in ("faithful", "unfaithful_material"):
        kept += rng.sample([c for c in rest if c["truth"] == truth], PER_TRUTH)
    return kept


def dump(cases: list[dict]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)


def main() -> int:
    cases = [json.loads(l) for l in (RUN / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    big = large(cases)
    out = {"cases-gt200.jsonl": big, "cases-gt200-short.jsonl": short(big)}
    status = 0
    for name, subset in out.items():
        path = RUN / name
        if "--check" in sys.argv:
            on_disk = [json.loads(l)["id"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            same = on_disk == [c["id"] for c in subset]
            print(f"{name}: {len(subset)} answers, {'same as the file' if same else 'DIFFERENT from the file'}")
            status |= 0 if same else 1
        else:
            path.write_text(dump(subset), encoding="utf-8", newline="\n")
            print(f"{name}: {len(subset)} answers written")
    return status


if __name__ == "__main__":
    sys.exit(main())
