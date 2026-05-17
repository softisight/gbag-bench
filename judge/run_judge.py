"""
GBAG Judge — scores model answers against the gold reference.

Usage:
    python judge/run_judge.py \\
        --dataset data/questions.jsonl \\
        --answers path/to/model_answers.jsonl \\
        --output path/to/scores.jsonl \\
        --judge anthropic   # or: openai

Input answers file (JSONL, one per line):
    {"id": "sakila-l1-01", "model_answer": "There are 200 actors..."}

Output (JSONL):
    {"id": "...", "gbag_score": 87.4, "faithfulness": 95, "completeness": 80,
     "insight": 70, "...justifications..."}

Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


JUDGE_PROMPT_PATH = Path(__file__).parent / "prompt.md"


def load_judge_system_prompt() -> str:
    """Extract the System prompt section from prompt.md."""
    text = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    marker = "## System prompt"
    idx = text.find(marker)
    if idx == -1:
        raise RuntimeError("Could not locate '## System prompt' in judge/prompt.md")
    return text[idx + len(marker):].strip()


def build_user_message(question: dict, model_answer: str) -> str:
    return (
        f"QUESTION:\n{question['question']}\n\n"
        f"SQL:\n{question['gold_sql']}\n\n"
        f"GOLD ANSWER:\n{question['gold_answer']}\n\n"
        f"EXPECTED INSIGHTS:\n"
        + "\n".join(f"- {i}" for i in question.get("expected_insights", []))
        + f"\n\nMODEL ANSWER:\n{model_answer}\n"
    )


def call_anthropic(system: str, user: str, model: str = "claude-sonnet-4-6") -> str:
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


def call_openai(system: str, user: str, model: str = "gpt-5") -> str:
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


def call_deepseek(system: str, user: str, model: str = "deepseek-chat") -> str:
    """DeepSeek API is OpenAI-compatible. Set DEEPSEEK_API_KEY."""
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def parse_judge_response(raw: str) -> dict:
    """Extract JSON object from the judge's response (tolerant of fences)."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    return json.loads(s)


def compute_gbag_score(scores: dict) -> float:
    return round(
        0.50 * scores["faithfulness"]
        + 0.30 * scores["completeness"]
        + 0.20 * scores["insight"],
        2,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True, help="Path to questions.jsonl")
    ap.add_argument("--answers", required=True, help="Path to model_answers.jsonl")
    ap.add_argument("--output", required=True, help="Where to write scores.jsonl")
    ap.add_argument("--judge", choices=["anthropic", "openai", "deepseek"], default="anthropic")
    ap.add_argument("--model", default=None, help="Override judge model id")
    ap.add_argument("--limit", type=int, default=0, help="Score only first N (debug)")
    args = ap.parse_args()

    dataset = {q["id"]: q for q in (json.loads(l) for l in Path(args.dataset).open(encoding="utf-8") if l.strip())}
    answers = [json.loads(l) for l in Path(args.answers).open(encoding="utf-8") if l.strip()]
    if args.limit:
        answers = answers[: args.limit]

    system = load_judge_system_prompt()
    caller = {"anthropic": call_anthropic, "openai": call_openai, "deepseek": call_deepseek}[args.judge]
    kwargs = {"model": args.model} if args.model else {}

    out = Path(args.output).open("w", encoding="utf-8")
    n_ok = n_err = 0

    for i, ans in enumerate(answers, 1):
        qid = ans["id"]
        q = dataset.get(qid)
        if not q:
            print(f"[{i}/{len(answers)}] {qid}: NOT IN DATASET — skipped", file=sys.stderr)
            continue
        user = build_user_message(q, ans["model_answer"])
        try:
            raw = caller(system, user, **kwargs)
            parsed = parse_judge_response(raw)
            score = compute_gbag_score(parsed)
            record = {"id": qid, "gbag_score": score, **parsed}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            n_ok += 1
            print(f"[{i}/{len(answers)}] {qid}: GBAG={score} (F={parsed['faithfulness']} C={parsed['completeness']} I={parsed['insight']})")
        except Exception as e:
            n_err += 1
            print(f"[{i}/{len(answers)}] {qid}: ERROR — {e}", file=sys.stderr)
            time.sleep(1)

    out.close()
    print(f"\nDone. {n_ok} scored, {n_err} errors.")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
