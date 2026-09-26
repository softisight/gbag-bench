"""Run the GBAG v0.6 judge over an answers file.

Usage (repo root):
    python -m judge.v06.run_v06 --dataset data/questions-reserve.jsonl \\
        --answers data/answers-reserve.jsonl --output runs/v0.6/dev/reserve-jev.jsonl --mode jev
    ... --mode lex     # the fallback: fixed lexicon, no model at all

Every output line records the verdict and, for each figure, the scores Jev gave, the
choices kept after the thresholds, the scope and its source, and the true values.
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

from judge.v05.result import load
from judge.v05.split import TRIGGERS_FILE, split_answer
from judge.v05.tables import check_tables

from . import jev, lex
from .decide import declaration, judge_unit, scope_of, verdict
from .units import units_of

VERSION = "0.6.0-dev"


def judge_answer(q: dict, answer: str, mode: str) -> dict:
    res = load(q)
    sp = split_answer(answer)
    decl = declaration(answer, res)
    results, models, cost = [], set(), 0.0
    n = 0
    unjudged: list[str] = []
    for c in sp.claims:
        if not units_of(c.text, c.context, 0, res.columns):
            unjudged.append(c.text)
        for u in units_of(c.text, c.context, n, res.columns):
            n += 1
            if u.forced_column:
                # a labelled field ("Total Amount: 19264.82"): column and family set by code
                family, column, reference, fam_src = "cell", u.forced_column, None, "code (labelled field)"
                scope, src = scope_of(c.text, None, decl)
                on_q, scores = True, {}
            elif mode == "jev":
                ans, meta = jev.ask(q["question"], c.context, c.text, u.raw, res.columns)
                models.add(meta.get("model"))
                cost += meta.get("cost") or 0
                family = jev.accepted(ans.get("family"))
                column = jev.accepted(ans.get("column"))
                column = None if column == "none" else column
                reference = jev.accepted(ans.get("reference"))
                scope, src = scope_of(c.text, jev.accepted(ans.get("scope")), decl)
                on_q = jev.bears_on_question(ans.get("on_question"))
                scores = {k: (v.get("probabilities") or v.get("noul")) for k, v in ans.items()}
                scores["confidence"] = {k: v["confidence"] for k, v in ans.items() if "confidence" in v}
                fam_src = "jev" if family else "jev uncertain"
            else:
                family, column, reference = lex.family_of(u), None, None
                scope, src = scope_of(c.text, None, decl)
                on_q, scores, fam_src = True, {}, "lexicon"
            results.append(judge_unit(u, res, family, fam_src, column, reference, scope, src, on_q, scores))
    table = check_tables(sp.table_lines, res)
    v = verdict(results, table, unjudged)
    return {**v, "declaration": decl,
            "units": [asdict(r) for r in results],
            "table": asdict(table),
            "coverage": {"sentences_selected": len(sp.claims), "sentences_discarded": len(sp.discarded),
                         "units": len(results),
                         "verified_true": sum(r.holds is True for r in results),
                         "false": sum(r.holds is False for r in results),
                         "undecided": sum(r.holds is None and r.family != "place" for r in results),
                         "places": sum(r.family == "place" for r in results)},
            "jev_models": sorted(m for m in models if m), "cost_usd": cost}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--mode", choices=["jev", "lex"], default="jev")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    qs = {json.loads(l)["id"]: json.loads(l) for l in open(args.dataset, encoding="utf-8") if l.strip()}
    answers = [json.loads(l) for l in open(args.answers, encoding="utf-8") if l.strip()]
    if args.only:
        answers = [a for a in answers if a["id"] == args.only]
    config = {"judge": "gbag-v0.6", "version": VERSION, "mode": args.mode,
              "jev_model": jev.MODEL if args.mode == "jev" else None,
              "thresholds": {"accept_confidence": jev.ACCEPT_CONF, "margin": jev.ACCEPT_MARGIN,
                             "on_question_not_bearing_at_most": jev.ON_Q_NO, "samples": jev.SAMPLES},
              "triggers_sha256": hashlib.sha256(TRIGGERS_FILE.read_bytes()).hexdigest()[:16],
              "dataset": args.dataset, "answers": args.answers}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for i, a in enumerate(answers, 1):
            t0 = time.time()
            rec = judge_answer(qs[a["id"]], a["model_answer"], args.mode)
            rec = {"id": a["id"], **rec, "seconds": round(time.time() - t0, 1),
                   "judge_config": {**config, "batch_position": i}}
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            cov = rec["coverage"]
            print(f"[{i}/{len(answers)}] {a['id']}: {rec['verdict']} (T{cov['verified_true']} F{cov['false']} "
                  f"U{cov['undecided']} P{cov['places']}) {rec['seconds']}s — {rec['reason'][:130]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
