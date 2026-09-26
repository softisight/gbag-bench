"""Build data/v07/targets.jsonl (PROTOCOL_v0.7.md): every target with its two truths,
computed on the frozen database. Run once, before any answer is generated.

Usage (repo root):  python scripts/build_v07_targets.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scorer.v07.targets import ROW_CAP, TARGETS, compute

QUESTIONS = ROOT / "data" / "questions-heldout.jsonl"
DB = ROOT / "databases" / "ledger.sqlite"
OUT = ROOT / "data" / "v07" / "targets.jsonl"


def main() -> int:
    qs = {json.loads(l)["id"]: json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()}
    con = sqlite3.connect(DB)
    seen: dict[str, int] = {}
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for qid, ask, typ, op in TARGETS:
            cur = con.execute(qs[qid]["gold_sql"])
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            t_all, t_shown = compute(op, rows), compute(op, rows[:ROW_CAP])
            seen[qid] = seen.get(qid, 0) + 1
            kind = "discriminating" if len(rows) > ROW_CAP and t_all != t_shown else "control"
            rec = {"tid": f"{qid}#{seen[qid]}", "qid": qid, "ask": ask, "type": typ, "op": list(op),
                   "n_rows": len(rows), "truth_all": t_all, "truth_shown": t_shown, "kind": kind}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{rec['tid']:18} {kind:15} all={t_all!s:>14}  shown={t_shown!s:>14}  {ask}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
