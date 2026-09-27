"""GBAG v0.7 — generate declared answers (PROTOCOL_v0.7.md). No judge: answers are scored
afterwards by scorer/v07 (scripts/score_v07.py).

For every target of data/v07/targets.jsonl, the model receives the v0.4 generation prompt
(question, executed SQL, result table capped at 200 rows, with the truncation stated) and a
closing instruction asking for the FINAL_ANSWER block. Arm A asks for value + scope; arm B
(priming check) for value only.

Usage (repo root):
    python scripts/generate_v07.py --provider openrouter --models openai/gpt-5.6-sol   # cloud: not for GBAG (D3)
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/generate_v07.py --provider ollama --models qwen3.6:latest gemma4:12b

PROTOCOL_v0.7 D5: the served-call metadata is kept per thread and stored under "served"
(it never overwrites "model"); local models run one after the other with an explicit
context window, and a prompt that fills it is flagged, never silently truncated.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.request
from collections.abc import MutableMapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))
import baseline_runner as br  # the v0.4 generation prompt and callers, unchanged
from scorer.v07.targets import ROW_CAP, load_questions, run_gold

TARGETS = ROOT / "data" / "v07" / "targets.jsonl"
OUT = ROOT / "runs" / "v0.7" / "answers"
LOCAL_MODELS = ["gemma4:12b"]   # D3: local only; D9: Bonsai 27B and Spark-X2.5-4B passed by name (runs/v0.7/queue_box.sh)
CLOUD_MODELS = ["anthropic/claude-fable-5", "openai/gpt-5.6-sol", "moonshotai/kimi-k3",
                "nvidia/nemotron-3-nano-30b-a3b", "qwen/qwen3-coder"]
COST_CAP_USD = 15.0
NUM_CTX = 16384          # Ollama truncates a longer prompt silently: set it, then check it
OLLAMA_TIMEOUT_S = 1800  # a 3060 with reasoning on can take minutes per answer


class _PerThread(MutableMapping):
    """baseline_runner.LAST_CALL, one dict per thread: the shared dict let a thread record
    another thread's model and cost (D2, D5)."""
    def __init__(self):
        self._local = threading.local()

    def _d(self) -> dict:
        if not hasattr(self._local, "d"):
            self._local.d = {}
        return self._local.d

    def __getitem__(self, k): return self._d()[k]
    def __setitem__(self, k, v): self._d()[k] = v
    def __delitem__(self, k): del self._d()[k]
    def __iter__(self): return iter(self._d())
    def __len__(self): return len(self._d())


br.LAST_CALL = _PerThread()


def call_ollama(system: str, user: str, model: str) -> tuple[str, int | None, int | None, dict]:
    """Ollama /api/generate with an explicit context window (baseline_runner's caller sets
    none, and the 200-row prompts exceed Ollama's default)."""
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    # D10: reasoning OFF for local models. Left at the runtime default, gemma4:12b looped
    # in its reasoning until the context was full (5 answers in 9, empty) at temperature 0.
    payload = {"model": model, "prompt": user, "system": system, "stream": False, "think": False,
               "options": {"temperature": 0, "num_ctx": NUM_CTX}}
    req = urllib.request.Request(f"{host}/api/generate", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as r:
        data = json.loads(r.read().decode("utf-8"))
    tin, tout = data.get("prompt_eval_count"), data.get("eval_count")
    meta = {"num_ctx": NUM_CTX, "think": False, "thinking_chars": len(data.get("thinking") or ""),
            "context_full": bool(tin and tin >= NUM_CTX - 8)}
    return (data.get("response") or "").strip(), tin, tout, meta


def call_openrouter(system: str, user: str, model: str) -> tuple[str, int | None, int | None, dict]:
    text, tin, tout = br.call_openrouter(system, user, model)
    return text, tin, tout, dict(br.LAST_CALL)

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
    qs = load_questions(ROOT)
    out, gold = [], {}
    for t in (json.loads(l) for l in TARGETS.read_text(encoding="utf-8").splitlines() if l.strip()):
        q = qs[t["qid"]]
        if t["qid"] not in gold:                # D7: each question on its own database, run once
            gold[t["qid"]] = run_gold(ROOT, q)
        cols, rows = gold[t["qid"]]
        for arm in ("A", "B"):
            out.append((t, arm, user_prompt(q, cols, rows[:ROW_CAP], len(rows), t["ask"], arm)))
    return out


_lock = threading.Lock()
_spent = [0.0]


def slug(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def run_model(model: str, provider: str, arms: list[str], runs: int, items: list) -> None:
    call = call_openrouter if provider == "openrouter" else call_ollama
    for run in range(1, runs + 1):
        for arm in arms:
            out = OUT / f"{slug(model)}-{arm}-r{run}.jsonl"
            # a failed call (box paused, transport) is retried on resume; its error row stays
            # in the file and is scored `error`, out of every denominator (D2)
            done = {r["tid"] for r in (json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip())
                    if not r.get("error")} if out.exists() else set()
            for t, a, prompt in items:
                if a != arm or t["tid"] in done:
                    continue
                if _spent[0] >= COST_CAP_USD:
                    print(f"cost cap {COST_CAP_USD} USD reached — stopping {model}", flush=True)
                    return
                t0, text, err, tin, tout, meta = time.time(), "", None, None, None, {}
                for attempt in range(3):
                    try:
                        text, tin, tout, meta = call(br.SYSTEM_PROMPT, prompt, model)
                        err = None
                        break
                    except Exception as e:  # transport or provider error: same prompt, retried
                        err = str(e)[:300]
                        time.sleep(5 * (attempt + 1))
                if meta.get("context_full"):
                    err = f"prompt filled the {NUM_CTX}-token context: possibly truncated"
                rec = {"tid": t["tid"], "arm": arm, "run": run, "model": model, "provider": provider,
                       "answer": text, "error": err, "input_tokens": tin, "output_tokens": tout,
                       "seconds": round(time.time() - t0, 1), "served": meta}
                with _lock:
                    _spent[0] += meta.get("cost_usd") or 0
                    with out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{model} arm {arm} run {run}: done (total spent {_spent[0]:.3f} USD)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--provider", choices=["openrouter", "ollama"], default="ollama")
    ap.add_argument("--arms", nargs="*", default=["A", "B"])
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()
    if args.models is None:
        args.models = LOCAL_MODELS if args.provider == "ollama" else CLOUD_MODELS
    OUT.mkdir(parents=True, exist_ok=True)
    items = prompts()
    if args.provider == "ollama":
        # one GPU: local models run one after the other
        for m in args.models:
            run_model(m, args.provider, args.arms, args.runs, items)
    else:
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
