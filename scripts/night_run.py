"""Overnight judge campaign: finish the gemma table, then measure the frontier rate.

Two things are missing after 2026-08-06 and both need GPU time we only have at night.

PHASE 1 — completeness. Five of the seven held-out models were scored by gemma4:31b under
v0.4.1; the pass was stopped after nemotron. Without qwen3-coder-480b and qwen3.6 the
cliff table has two holes, and a table with holes invites the reader to assume the missing
rows were dropped because they were inconvenient.

PHASE 2 — the frontier rate. Same day, same case, same prompt, same 3211 input tokens,
same host, seed 42, temperature 0: faithfulness 40 when the case was the first call of the
process, 100 when any other case preceded it. The shared system prompt is computed cold on
the first request and served from the prefix cache afterwards, and that numerical
difference flips verdicts that sit on the contradicted/unverifiable boundary.

A case whose verdict changes between the two conditions is a FRONTIER case. We do not know
how many there are, and the answer decides what may be published:

  * few    -> document the constraint (replay the same list in the same order) and move on
  * many   -> no average from this campaign is publishable as it stands

Phase 2 therefore replays every case ALONE — one process per case, so each is a cold first
call — and diffs against the batch scores already on disk. Three models are covered rather
than seven: the rate must be read across models, but seven would not fit one night, and a
rate measured on 45 judgments is already enough to tell "few" from "many". Extend MODELS
if a longer window is available.

Nothing here is a scoring decision: it re-runs an existing judge on existing answers and
compares. Usage (from the repo root, GPU free):

    set OLLAMA_HOST=http://192.168.0.112:11434
    python scripts/night_run.py

Resumable: any output file already complete is skipped, so an interrupted night can be
relaunched with the same command.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JUDGE = ["python", str(ROOT / "judge" / "run_judge.py")]
COMMON = ["--judge", "ollama", "--model", "gemma4:31b",
          "--prompt", str(ROOT / "judge" / "prompt-v041.md")]
DATASET = ROOT / "data" / "questions-heldout.jsonl"

PHASE1 = ["qwen3-coder-480b", "qwen3.6"]
PHASE2 = ["nemotron-3-nano-30b", "claude-fable-5", "gemma4-12b"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def lines(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def run(args: list[str]) -> bool:
    r = subprocess.run(JUDGE + args + COMMON, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log(f"  ECHEC: {(r.stderr or '').strip()[-300:]}")
    return r.returncode == 0


def phase1() -> None:
    log("=== PHASE 1 — completer la table gemma (2 modeles x 15) ===")
    for m in PHASE1:
        ans = ROOT / "runs" / f"{m}-heldout.jsonl"
        out = ROOT / "runs" / f"{m}-heldout.scored-gemma31-v041.jsonl"
        if len(lines(out)) >= len(lines(ans)):
            log(f"{m}: deja complet, saute")
            continue
        log(f"{m}: {len(lines(ans))} cas en lot...")
        run(["--dataset", str(DATASET), "--answers", str(ans), "--output", str(out), "--resume"])
        log(f"{m}: {len(lines(out))} scores")


def phase2() -> None:
    log("=== PHASE 2 — rejeu ISOLE, un appel a froid par cas ===")
    qs = {q["id"]: q for q in lines(DATASET)}
    for m in PHASE2:
        ans = {a["id"]: a for a in lines(ROOT / "runs" / f"{m}-heldout.jsonl")}
        out = ROOT / "runs" / f"{m}-heldout.scored-gemma31-v041-isolated.jsonl"
        done = {d["id"] for d in lines(out)}
        todo = [i for i in ans if i not in done]
        if not todo:
            log(f"{m}: deja complet, saute")
            continue
        log(f"{m}: {len(todo)} cas a rejouer isolement")
        with out.open("a", encoding="utf-8") as fout:
            for qid in todo:
                if qid not in qs:
                    continue
                with tempfile.TemporaryDirectory() as td:
                    dq, da, do = Path(td) / "q.jsonl", Path(td) / "a.jsonl", Path(td) / "o.jsonl"
                    dq.write_text(json.dumps(qs[qid], ensure_ascii=False) + "\n", encoding="utf-8")
                    da.write_text(json.dumps(ans[qid], ensure_ascii=False) + "\n", encoding="utf-8")
                    if not run(["--dataset", str(dq), "--answers", str(da), "--output", str(do)]):
                        continue
                    for rec in lines(do):
                        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        fout.flush()
                        log(f"  {m}/{qid}: F={rec['faithfulness']} GBAG={rec['gbag_score']}")


def report() -> None:
    log("=== TAUX DE CAS FRONTIERES ===")
    tot = div = 0
    for m in PHASE2:
        b = {d["id"]: d for d in lines(ROOT / "runs" / f"{m}-heldout.scored-gemma31-v041.jsonl")}
        i = {d["id"]: d for d in lines(ROOT / "runs" / f"{m}-heldout.scored-gemma31-v041-isolated.jsonl")}
        common = sorted(set(b) & set(i))
        d = [k for k in common if abs(b[k]["gbag_score"] - i[k]["gbag_score"]) > 0.01]
        tot += len(common)
        div += len(d)
        print(f"   {m:22} {len(d)}/{len(common)} divergent")
        for k in d:
            print(f"      {k:16} lot F={b[k]['faithfulness']:3} GBAG={b[k]['gbag_score']:5}"
                  f"   isole F={i[k]['faithfulness']:3} GBAG={i[k]['gbag_score']:5}")
    if tot:
        print(f"\n   TAUX GLOBAL : {div}/{tot} = {100*div/tot:.1f} % des jugements sont sensibles a la position")


if __name__ == "__main__":
    t0 = time.time()
    phase1()
    phase2()
    report()
    log(f"termine en {(time.time()-t0)/3600:.1f} h")
    sys.exit(0)
