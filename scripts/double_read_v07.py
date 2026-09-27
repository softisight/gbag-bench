"""GBAG v0.7 — DOUBLE READING of the declared answers (PROTOCOL_v0.7.md, D13).

The truths are computed by SQL; the only step that can go wrong is READING what the model
declared. The code reads the FINAL_ANSWER block (scorer/v07/score.py). Here an AI reads it
again, independently: it never sees the code's reading, only the end of the answer, and it
fills fixed fields (block found / value as written / declared scope among fixed options).
Both readings then go through the SAME classification rules (`classify_parsed`).

  * agree    -> the verdict stands;
  * disagree -> the answer is CONTESTED: set apart, counted, never corrected in our favour.
The agreement rate is the published reliability figure of the algorithmic reading.

Reader: a LOCAL model (D3), reasoning off, temperature 0, JSON schema imposed by Ollama.

Usage (repo root):
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/double_read_v07.py --sample 200    # the stratified sample first (D13)
    python scripts/double_read_v07.py                 # then every answer not yet read
    python scripts/double_read_v07.py --report
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scorer.v07.score import classify, classify_parsed

TARGETS = ROOT / "data" / "v07" / "targets.jsonl"
ANSWERS = ROOT / "runs" / "v0.7" / "answers"
OUT = ROOT / "runs" / "v0.7" / "double-reading.jsonl"
READER = "gemma4:12b"
TAIL_CHARS = 2000

INSTRUCTIONS = (
    "You read the END of an answer written by another AI. That answer was asked to finish with a block:\n"
    "FINAL_ANSWER\n"
    "value: <a number, date or identifier, or NONE>\n"
    "scope: <all_data | rows_shown | cannot_determine>   (sometimes the scope line is not requested)\n\n"
    "Report ONLY what that final block declares. Do not judge whether it is right. Do not compute anything.\n"
    "- block_found: true if the answer ends with such a FINAL_ANSWER block declaring a value, else false.\n"
    "- value: the declared value copied EXACTLY as written in the block, with any words written next to it "
    "on the same line; \"NONE\" if the block declares NONE or declines; \"\" if there is no block.\n"
    "- scope: the word written on the block's \"scope:\" line (all_data, rows_shown or cannot_determine). "
    "If the block has NO \"scope:\" line, answer not_stated. Never infer a scope from anything else.\n"
)
SCHEMA = {
    "type": "object",
    "properties": {
        "block_found": {"type": "boolean"},
        "value": {"type": "string"},
        "scope": {"type": "string", "enum": ["all_data", "rows_shown", "cannot_determine", "not_stated"]},
    },
    "required": ["block_found", "value", "scope"],
}


def read_with_ai(answer: str) -> dict:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    tail = answer[-TAIL_CHARS:]
    payload = {"model": READER, "system": INSTRUCTIONS,
               "prompt": "END OF THE ANSWER:\n<<<\n" + tail + "\n>>>", "stream": False,
               "think": False, "format": SCHEMA, "options": {"temperature": 0, "num_ctx": 8192}}
    req = urllib.request.Request(f"{host}/api/generate", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.loads(r.read().decode("utf-8"))["response"])


def as_parsed(ai: dict) -> dict | None:
    """The AI's reading in the parser's shape: None = no block; scope None = not stated."""
    if not ai.get("block_found"):
        return None
    scope = ai.get("scope")
    return {"value": (ai.get("value") or "").strip(), "scope": None if scope == "not_stated" else scope}


def answers():
    for f in sorted(ANSWERS.glob("*.jsonl")):
        model = f.stem.rsplit("-", 2)[0].replace("__", "/")
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("error"):
                    yield model, r


def sample(items: list, size: int, seed: int = 7) -> list:
    """A fixed, stratified sample: the same share of every (model, arm), drawn with a fixed
    seed, so that anyone can redraw it."""
    import random
    groups = collections.defaultdict(list)
    for m, r in items:
        groups[(m, r["arm"])].append((m, r))
    rng = random.Random(seed)
    out, total = [], len(items)
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda x: (x[1]["run"], x[1]["tid"]))
        k = max(1, round(size * len(g) / total))
        out += rng.sample(g, min(k, len(g)))
    return out


def run(size: int | None) -> None:
    targets = {t["tid"]: t for t in (json.loads(l) for l in TARGETS.read_text(encoding="utf-8").splitlines() if l.strip())}
    done = set()
    if OUT.exists():
        done = {(d["model"], d["arm"], d["run"], d["tid"])
                for d in (json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip())}
    pool = list(answers())
    if size:
        pool = sample(pool, size)
    todo = [(m, r) for m, r in pool if (m, r["arm"], r["run"], r["tid"]) not in done]
    print(f"{len(todo)} answers to read with {READER}", flush=True)
    for i, (model, r) in enumerate(todo, 1):
        t = targets[r["tid"]]
        code_class, code_parsed = classify(r["answer"], t, r["arm"])
        t0 = time.time()
        try:
            ai = read_with_ai(r["answer"])
            err = None
        except Exception as e:  # a failed reading is recorded, retried on the next run
            ai, err = {}, str(e)[:200]
        ai_class, ai_parsed = classify_parsed(as_parsed(ai), t, r["arm"]) if not err else ("error", None)
        rec = {"model": model, "arm": r["arm"], "run": r["run"], "tid": r["tid"], "kind": t["kind"],
               "code_class": code_class, "code_parsed": code_parsed, "ai_reading": ai, "ai_class": ai_class,
               "agree": (ai_class == code_class) if not err else None, "reader": READER,
               "seconds": round(time.time() - t0, 1), "error": err}
        if not err:
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if i % 50 == 0:
            print(f"{i}/{len(todo)}", flush=True)
    print("all read", flush=True)


def report() -> None:
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(rows)
    agree = sum(r["agree"] for r in rows)
    print(f"DOUBLE READING — {n} answers, reader {rows[0]['reader'] if rows else '?'}")
    print(f"  class agreement: {agree}/{n} = {100 * agree / n:.1f} %  (contested: {n - agree})")
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by[r["model"]][0] += r["agree"]
        by[r["model"]][1] += 1
    for m, (a, t) in sorted(by.items()):
        print(f"  {m:34} {a}/{t} = {100 * a / t:.1f} %")
    pairs = collections.Counter((r["code_class"], r["ai_class"]) for r in rows if not r["agree"])
    print("  disagreements (code -> AI):", dict(pairs))
    for r in [r for r in rows if not r["agree"]][:25]:
        print(f"   {r['model'][:24]:24} {r['arm']} {r['tid']:18} code={r['code_class']:12} {r['code_parsed']}  "
              f"AI={r['ai_class']:12} {r['ai_reading']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--sample", type=int, default=None, help="stratified sample size (D13: 200 first)")
    args = ap.parse_args()
    report() if args.report else run(args.sample)
