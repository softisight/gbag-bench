"""DIRECTIVE_032 (DeskInsightCS, first numbered 031) session B (DeskInsightCS) — the measurement set: every arbitrated GBAG
answer whose verdict counts (faithful / unfaithful_material), with its question and gold
SQL. Minor and disputed verdicts are excluded, as in every GBAG evaluation.

Writes runs/031b/cases.jsonl: {id, set, database, level, question, gold_sql, answer, truth}.

Usage (repo root):  python scripts/export_031b_cases.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "t7": ("runs/judge-calibration/t7-q.jsonl", "runs/judge-calibration/t7-a.jsonl", "data/judge-truth-set.jsonl"),
    "reserve": ("data/questions-reserve.jsonl", "data/answers-reserve.jsonl", "data/verdicts-reserve.jsonl"),
    "test05": ("data/sealed/test-v05/questions.jsonl", "data/sealed/test-v05/answers.jsonl",
               "data/sealed/test-v05/verdicts.jsonl"),
    "test06": ("data/sealed/test-v06/questions.jsonl", "data/sealed/test-v06/answers.jsonl",
               "data/sealed/test-v06/verdicts.jsonl"),
}
OUT = ROOT / "runs" / "031b" / "cases.jsonl"


def lines(rel: str) -> list[dict]:
    return [json.loads(l) for l in (ROOT / rel).read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for name, (qf, af, tf) in SETS.items():
            qs = {q["id"]: q for q in lines(qf)}
            truth = {t["id"]: t["verdict"] for t in lines(tf)}
            for a in lines(af):
                v = truth.get(a["id"])
                if v not in ("faithful", "unfaithful_material"):
                    continue
                q = qs[a["id"]]
                f.write(json.dumps({"id": a["id"], "set": name, "database": q["database"],
                                    "level": int(q.get("level") or 1), "question": q["question"],
                                    "gold_sql": q["gold_sql"], "answer": a["model_answer"], "truth": v},
                                   ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} cases -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
