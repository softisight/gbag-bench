"""Run the GBAG v0.5 verifying judge over an answers file.

Usage (repo root):
    python -m judge.v05.run_v05 --dataset data/questions-reserve.jsonl \\
        --answers data/answers-reserve.jsonl --output runs/v0.5/dev/reserve.jsonl \\
        --backend ollama --model qwen3.8:27b

Every output line records the verdict AND its evidence: each sentence, its fact sheet,
the scope and where the scope came from, the true value computed, and the table cells
checked. A condemnation is only ever the consequence of a recorded proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from .decide import declaration, judge_claims, verdict_for
from .result import load
from .sheet import TYPES, validate
from .split import TRIGGERS_FILE, split_answer
from .tables import check_tables
from .translate import PROMPT_SHA, translate

VERSION = "0.5.0-dev"


def judge_answer(q: dict, answer: str, backend: str, model: str) -> dict:
    res = load(q)
    sp = split_answer(answer)
    decl = declaration(answer, res)
    pairs, calls = [], []
    for c in sp.claims:
        print(f"    translating {c.idx + 1}/{len(sp.claims)}", file=sys.stderr, flush=True)
        sheets, meta = translate(backend, model, q["question"], res.describe(), c.context, c.text, res.columns)
        calls.append(meta)
        for s in sheets:
            pairs.append((c.text, validate(s, c.text, c.context)))
    claims = judge_claims(pairs, res, decl)
    table = check_tables(sp.table_lines, res)
    v = verdict_for(claims, table)
    return {
        "verdict": v.verdict, "band": v.band, "faithfulness": v.faithfulness, "reason": v.reason,
        "declaration": decl,
        "claims": [asdict(c) for c in claims],
        "table": asdict(table),
        "coverage": {
            "sentences_selected": len(sp.claims), "sentences_discarded": len(sp.discarded),
            "sheets": len(claims),
            "verified_true": sum(c.holds is True for c in claims),
            "false": sum(c.holds is False for c in claims),
            "undecided": sum(c.holds is None and c.scope != "interpretation" for c in claims),
            "interpretation": sum(c.scope == "interpretation" for c in claims),
            "rejected": sum(c.scope_source == "rejected" for c in claims),
        },
        "discarded_sentences": sp.discarded,
        "calls": {"n": len(calls), "in": sum(m.get("in") or 0 for m in calls),
                  "out": sum(m.get("out") or 0 for m in calls),
                  "cost_usd": sum(m.get("cost") or 0 for m in calls),
                  "providers": sorted({m.get("provider") for m in calls if m.get("provider")}),
                  "unparseable": sum(1 for m in calls if "unparseable" in m)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--backend", choices=["ollama", "openrouter"], default="ollama")
    ap.add_argument("--model", default="qwen3.8:27b")
    ap.add_argument("--only", default=None, help="judge a single answer id")
    args = ap.parse_args()

    qs = {json.loads(l)["id"]: json.loads(l) for l in open(args.dataset, encoding="utf-8") if l.strip()}
    answers = [json.loads(l) for l in open(args.answers, encoding="utf-8") if l.strip()]
    if args.only:
        answers = [a for a in answers if a["id"] == args.only]
    config = {"judge": "gbag-v0.5-verifying", "version": VERSION, "backend": args.backend,
              "model": args.model, "translate_prompt_sha256": PROMPT_SHA,
              "triggers_sha256": hashlib.sha256(TRIGGERS_FILE.read_bytes()).hexdigest()[:16],
              "types": TYPES, "dataset": args.dataset, "answers": args.answers}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for i, a in enumerate(answers, 1):
            t0 = time.time()
            rec = judge_answer(qs[a["id"]], a["model_answer"], args.backend, args.model)
            rec = {"id": a["id"], **rec, "seconds": round(time.time() - t0, 1),
                   "judge_config": {**config, "batch_position": i}}
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            cov = rec["coverage"]
            print(f"[{i}/{len(answers)}] {a['id']}: {rec['verdict']} "
                  f"(true {cov['verified_true']}, false {cov['false']}, undecided {cov['undecided']}, "
                  f"table {rec['table']['cells_checked']} cells/{len(rec['table']['mismatches'])} bad) "
                  f"{rec['seconds']}s — {rec['reason'][:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
