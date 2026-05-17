"""
GBAG Baseline Runner — neutral reference implementation.

Executes the gold_sql of each question against the SQLite database, then asks
a model to produce a natural-language answer. Writes model_answers.jsonl,
which can then be scored with judge/run_judge.py.

This runner is independent from any commercial product. Anyone with an API key
can reproduce GBAG results in a few minutes.

Usage:
    python examples/baseline_runner.py \\
        --dataset data/questions.jsonl \\
        --db-dir databases/ \\
        --output runs/claude-sonnet-4-6.jsonl \\
        --provider anthropic \\
        --model claude-sonnet-4-6

    python examples/baseline_runner.py \\
        --dataset data/questions.jsonl \\
        --db-dir databases/ \\
        --output runs/qwen3-14b.jsonl \\
        --provider ollama \\
        --model qwen3:14b

Expected DB filenames in --db-dir:
    sakila.sqlite, chinook.sqlite, northwind.sqlite

Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY for cloud providers.
Ollama provider needs a local server on http://localhost:11434.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


SYSTEM_PROMPT = (
    "You are a business intelligence assistant. The user asked a question, "
    "the SQL was executed for you, and the result is provided. Produce a clear, "
    "faithful natural-language answer in English. Do not invent numbers. "
    "Be concise but include the key figures and any visible trend."
)


def execute_sql(db_path: Path, sql: str, row_cap: int = 200) -> tuple[list[str], list[tuple]]:
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(row_cap)
        return cols, rows
    finally:
        con.close()


def format_result_as_markdown(cols: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "(no rows)"
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def build_user_prompt(question: str, sql: str, cols: list[str], rows: list[tuple]) -> str:
    return (
        f"USER QUESTION:\n{question}\n\n"
        f"EXECUTED SQL:\n{sql}\n\n"
        f"RESULT ({len(rows)} rows shown):\n{format_result_as_markdown(cols, rows)}\n\n"
        "Write the answer now."
    )


def call_anthropic(system: str, user: str, model: str) -> str:
    from anthropic import Anthropic
    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def call_openai(system: str, user: str, model: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def call_ollama(system: str, user: str, model: str) -> str:
    import urllib.request
    body = json.dumps({
        "model": model,
        "prompt": user,
        "system": system,
        "stream": False,
        "options": {"temperature": 0, "think": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("response", "").strip()


CALLERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "ollama": call_ollama,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--db-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--provider", choices=list(CALLERS), required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    dataset = [json.loads(l) for l in Path(args.dataset).open(encoding="utf-8") if l.strip()]
    if args.limit:
        dataset = dataset[: args.limit]

    db_dir = Path(args.db_dir)
    caller = CALLERS[args.provider]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out = Path(args.output).open("w", encoding="utf-8")
    n_ok = n_err = 0

    for i, q in enumerate(dataset, 1):
        qid = q["id"]
        db_path = db_dir / f"{q['database']}.sqlite"
        if not db_path.exists():
            print(f"[{i}/{len(dataset)}] {qid}: missing DB {db_path}", file=sys.stderr)
            n_err += 1
            continue
        try:
            cols, rows = execute_sql(db_path, q["gold_sql"])
            user = build_user_prompt(q["question"], q["gold_sql"], cols, rows)
            t0 = time.time()
            answer = caller(SYSTEM_PROMPT, user, args.model)
            dt = round(time.time() - t0, 2)
            out.write(json.dumps({
                "id": qid,
                "model": args.model,
                "provider": args.provider,
                "model_answer": answer.strip(),
                "duration_seconds": dt,
            }, ensure_ascii=False) + "\n")
            out.flush()
            n_ok += 1
            print(f"[{i}/{len(dataset)}] {qid}: ok ({dt}s)")
        except Exception as e:
            n_err += 1
            print(f"[{i}/{len(dataset)}] {qid}: ERROR — {e}", file=sys.stderr)
            time.sleep(2)

    out.close()
    print(f"\nDone. {n_ok} answered, {n_err} errors. Output: {args.output}")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
