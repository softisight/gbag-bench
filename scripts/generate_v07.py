"""GBAG v0.7 — generate declared answers (PROTOCOL_v0.7.md). No judge: answers are scored
afterwards by scorer/v07 (scripts/score_v07.py).

For every target of data/v07/targets.jsonl, the model receives the v0.4 generation prompt
(question, executed SQL, result table capped at 200 rows, with the truncation stated) and a
closing instruction asking for the FINAL_ANSWER block. Arm A asks for value + scope; arm B
(priming check) for value only.

Usage (repo root):
    python scripts/generate_v07.py                       # every cloud model, both arms, 2 runs
    python scripts/generate_v07.py --models openai/gpt-5.6-sol --arms A --runs 1
    python scripts/generate_v07.py --provider ollama --models qwen3.6:latest   # later, local
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))
import baseline_runner as br  # the v0.4 generation prompt and callers, unchanged
from scorer.v07.targets import ROW_CAP

TARGETS = ROOT / "data" / "v07" / "targets.jsonl"
QUESTIONS = ROOT / "data" / "questions-heldout.jsonl"
DB = ROOT / "databases" / "ledger.sqlite"
OUT = ROOT / "runs" / "v0.7" / "answers"
CLOUD_MODELS = ["anthropic/claude-fable-5", "openai/gpt-5.6-sol", "moonshotai/kimi-k3",
                "nvidia/nemotron-3-nano-30b-a3b", "qwen/qwen3-coder"]
COST_CAP_USD = 15.0

BLOCK_A = (
    "End your answer with exactly this block, where `value` is {ask}:\n"
    "FINAL_ANSWER\n"
    "value: <the number, date or identifier, with numbers written in full digits, or NONE>\n"
    "scope: <all_data | rows_shown | cannot_determine>   (which rows your value is computed from)\n"
)
BLOCK_B = (
    "End your answer with exactly this block, where `value` is {ask}:\n"
    "FINAL_ANSWER\n"
    "value: <the number, date or identifier, with numbers written in full digits, or NONE>\n"
)


def user_prompt(q: dict, cols: list[str], shown: list[tuple], n_rows: int, ask: str, arm: str) -> str:
    header = (f"RESULT (first {len(shown)} of {n_rows} rows shown)" if n_rows > len(shown)
              else f"RESULT (all {n_rows} rows)")
    return (f"USER QUESTION:\n{q['question']}\n\n"
            f"EXECUTED SQL:\n{q['gold_sql']}\n\n"
            f"{header}:\n{br.format_result_as_markdown(cols, shown)}\n\n"
            + (BLOCK_A if arm == "A" else BLOCK_B).format(ask=ask) + "\nWrite the answer now.")


def prompts() -> list[tuple[dict, str, str]]:
    qs = {json.loads(l)["id"]: json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()}
    con = sqlite3.connect(DB)
    out = []
    for t in (json.loads(l) for l in TARGETS.read_text(encoding="utf-8").splitlines() if l.strip()):
        q = qs[t["qid"]]
        cur = con.execute(q["gold_sql"])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        for arm in ("A", "B"):
            out.append((t, arm, user_prompt(q, cols, rows[:ROW_CAP], len(rows), t["ask"], arm)))
    return out


_lock = threading.Lock()
_spent = [0.0]


def slug(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def run_model(model: str, provider: str, arms: list[str], runs: int, items: list) -> None:
    call = br.call_openrouter if provider == "openrouter" else br.call_ollama
    for run in range(1, runs + 1):
        for arm in arms:
            out = OUT / f"{slug(model)}-{arm}-r{run}.jsonl"
            done = {json.loads(l)["tid"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
            for t, a, prompt in items:
                if a != arm or t["tid"] in done:
                    continue
                if _spent[0] >= COST_CAP_USD:
                    print(f"cost cap {COST_CAP_USD} USD reached — stopping {model}", flush=True)
                    return
                t0, text, err, tin, tout = time.time(), "", None, None, None
                for attempt in range(3):
                    try:
                        text, tin, tout = call(br.SYSTEM_PROMPT, prompt, model)
                        err = None
                        break
                    except Exception as e:  # transport or provider error: same prompt, retried
                        err = str(e)[:300]
                        time.sleep(5 * (attempt + 1))
                meta = dict(br.LAST_CALL) if provider == "openrouter" else {}
                rec = {"tid": t["tid"], "arm": arm, "run": run, "model": model, "answer": text, "error": err,
                       "input_tokens": tin, "output_tokens": tout, "seconds": round(time.time() - t0, 1), **meta}
                with _lock:
                    _spent[0] += meta.get("cost_usd") or 0
                    with out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{model} arm {arm} run {run}: done (total spent {_spent[0]:.3f} USD)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=CLOUD_MODELS)
    ap.add_argument("--provider", choices=["openrouter", "ollama"], default="openrouter")
    ap.add_argument("--arms", nargs="*", default=["A", "B"])
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    items = prompts()
    threads = [threading.Thread(target=run_model, args=(m, args.provider, args.arms, args.runs, items))
               for m in args.models]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    print(f"all done — {_spent[0]:.3f} USD", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
