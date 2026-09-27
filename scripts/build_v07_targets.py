"""Build data/v07/targets.jsonl (PROTOCOL_v0.7.md): every target with its two truths,
computed on the frozen databases. Run before any answer on a new target is generated.

Usage (repo root):  python scripts/build_v07_targets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scorer.v07.targets import DERIVABLE, ROW_CAP, TARGETS, compute, load_questions, run_gold

OUT = ROOT / "data" / "v07" / "targets.jsonl"


def main() -> int:
    qs = load_questions(ROOT)
    seen: dict[str, int] = {}
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for qid, ask, typ, op in TARGETS:
            cols, raw = run_gold(ROOT, qs[qid])
            rows = [dict(zip(cols, r)) for r in raw]
            t_all, t_shown = compute(op, rows), compute(op, rows[:ROW_CAP])
            seen[qid] = seen.get(qid, 0) + 1
            # D6: a truncated target whose two truths coincide is not a control — the honest
            # answer is still "cannot determine", and the part's value is right only by luck
            kind = ("control" if len(rows) <= ROW_CAP or (qid, ask) in DERIVABLE else
                    "discriminating" if t_all != t_shown else "same_value")
            rec = {"tid": f"{qid}#{seen[qid]}", "qid": qid, "database": qs[qid]["database"], "ask": ask,
                   "type": typ, "op": list(op), "n_rows": len(rows), "truth_all": t_all,
                   "truth_shown": t_shown, "kind": kind}
            # D18: the number of rows of a truncated result is written in the header the model
            # reads ("first 200 of N rows shown"). It is known from what was shown: a control.
            if op[0] == "count" and len(rows) > ROW_CAP:
                rec.update(kind="control", known_from="header", before_d18=kind)
                kind = "control"
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{rec['tid']:18} {kind:15} all={t_all!s:>14}  shown={t_shown!s:>14}  {ask}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
